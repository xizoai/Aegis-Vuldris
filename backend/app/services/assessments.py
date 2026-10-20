"""Security test, execution, finding, evidence, and report service operations."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.errors import (
    AssessmentNotFoundError,
    ExecutionBindingError,
    ProjectNotFoundError,
)
from app.models.evidence import Evidence
from app.models.execution import Execution, ExecutionStatus
from app.models.execution_step import ExecutionStep
from app.models.external_scan import ExternalScan
from app.models.finding import Finding, FindingConfirmation, FindingStatus
from app.models.project import Project
from app.models.report import Report
from app.models.target import Target, TargetStatus
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas import (
    EvidenceCreate,
    ExecutionCreate,
    ExecutionStepResponse,
    FindingCreate,
    FindingTriageRequest,
    FindingUpdate,
    ReportCreate,
    SecurityTestCreate,
    SecurityTestUpdate,
    TestTriageStats,
)
from app.services.audit import record_audit_event
from app.services.confirmation import (
    apply_confirmation,
    recompute_execution_result,
)
from app.services.projects import ensure_project_access
from app.services.redaction import scan
from app.services.severity_scorer import compute_automatic_severity


def _finding_project_id(session: Session, finding: Finding) -> UUID:
    """Return the project a finding belongs to, whichever origin it has.

    A finding comes from a native execution or an external scan (the database
    enforces exactly one), and both authorize through their owning project. A
    finding whose origin row is gone is treated as not found rather than as
    unowned: there is nothing left to authorize against.
    """

    if finding.execution_id is not None:
        execution = session.get(Execution, finding.execution_id)
        if execution is not None:
            return execution.project_id
    elif finding.external_scan_id is not None:
        scan = session.get(ExternalScan, finding.external_scan_id)
        if scan is not None:
            return scan.project_id
    raise AssessmentNotFoundError()


def _require_project(session: Session, user: User, project_id: UUID) -> Project:
    """Authorize read access to a project."""

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "read")
    return project


def _require_project_write(session: Session, user: User, project_id: UUID) -> Project:
    """Authorize a state-changing operation on a project.

    Read access is not sufficient: a VIEWER must not create tests, executions,
    findings, evidence, or reports, nor modify or delete them. Naming the
    operation keeps the mutation explicit at each call site.
    """

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "update")
    return project


def require_finding_read(session: Session, finding: Finding, user: User) -> UUID:
    """Authorize reading a finding and return its project id.

    A finding comes from a native execution or an external scan; both
    authorize through the project that owns their origin row.
    """

    project_id = _finding_project_id(session, finding)
    _require_project(session, user, project_id)
    return project_id


def _require_project_test(session: Session, project_id: UUID, test_id: UUID) -> None:
    """Ensure a security test belongs to the given project."""

    test = session.get(SecurityTest, test_id)
    if test is None or test.project_id != project_id:
        raise AssessmentNotFoundError()


def _require_project_target(session: Session, project_id: UUID, target_id: UUID) -> Target:
    """Ensure a target belongs to the given project and is usable.

    Targets are a separate resource from projects, so an execution can name one
    that lives in a different project. Without this check the execution engine
    would resolve that target's stored credentials and send attacker-chosen
    prompts to another tenant's model endpoint.

    Returns the target so callers can validate the test/target pairing without
    a second lookup.
    """

    target = session.get(Target, target_id)
    if target is None or target.project_id != project_id:
        raise AssessmentNotFoundError()
    return target


def validate_execution_binding(
    test: SecurityTest | None,
    target: Target | None,
) -> None:
    """Validate that a security test can actually be run against a target.

    Ownership is checked separately. This covers the pairing itself: the target
    must be active and must advertise every capability the test requires.

    Provider identity is deliberately **not** checked. An attack case is a set
    of prompts — "reveal your system prompt" means the same to an Ollama model
    as to a hosted one — so requiring the two providers to match made every
    bundled test (all 224 declare ``openai_compatible``) unrunnable against a
    local model, which is the target most people start with. The capability
    check already rejects genuinely incompatible pairings, such as a test
    needing ``vision`` against a text-only target.
    """

    if test is None or target is None:
        return

    if target.status != TargetStatus.ACTIVE:
        raise ExecutionBindingError(
            f"target is {target.status.value!r}; reactivate it before running tests"
        )

    # Capability declarations are advisory. An undeclared list means "not
    # stated", not "incapable", so it must not restrict anything -- otherwise
    # every UI-created target (which declares nothing) could run no bundled
    # test, since all 224 of them require ``chat``. Declared capabilities do
    # restrict, which is how a vision test is kept off a text-only target.
    declared = set(target.capabilities or ())
    if not declared:
        return

    required = set(test.required_capabilities or ())
    missing = sorted(required - declared)
    if missing:
        raise ExecutionBindingError(
            f"target does not advertise required capabilit"
            f"{'y' if len(missing) == 1 else 'ies'}: {', '.join(missing)}"
        )


def create_security_test(
    session: Session,
    project_id: UUID,
    payload: SecurityTestCreate,
    user: User,
) -> SecurityTest:
    _require_project_write(session, user, project_id)
    test = SecurityTest(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        provider=payload.provider,
        required_capabilities=payload.required_capabilities,
        config=payload.config,
    )
    session.add(test)
    session.commit()
    session.refresh(test)
    record_audit_event(
        session,
        actor_id=user.id,
        action="security_test.created",
        resource_type="security_test",
        resource_id=str(test.id),
        event_metadata={"project_id": str(project_id)},
    )
    return test


def get_security_test(session: Session, test_id: UUID, user: User) -> SecurityTest:
    test = session.get(SecurityTest, test_id)
    if test is None:
        raise AssessmentNotFoundError()
    _require_project(session, user, test.project_id)
    return test


def list_security_tests(session: Session, project_id: UUID, user: User) -> list[SecurityTest]:
    _require_project(session, user, project_id)
    return list(
        session.scalars(
            select(SecurityTest)
            .where(SecurityTest.project_id == project_id)
            .order_by(SecurityTest.created_at, SecurityTest.id)
        ).all()
    )


def update_security_test(
    session: Session,
    test_id: UUID,
    payload: SecurityTestUpdate,
    user: User,
) -> SecurityTest:
    test = get_security_test(session, test_id, user)
    _require_project_write(session, user, test.project_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(test, field, value)
    session.commit()
    session.refresh(test)
    return test


def delete_security_test(session: Session, test_id: UUID, user: User) -> bool:
    test = get_security_test(session, test_id, user)
    _require_project_write(session, user, test.project_id)
    session.delete(test)
    session.commit()
    record_audit_event(
        session,
        actor_id=user.id,
        action="security_test.deleted",
        resource_type="security_test",
        resource_id=str(test_id),
        event_metadata={"project_id": str(test.project_id)},
    )
    return True


def create_execution(
    session: Session,
    project_id: UUID,
    payload: ExecutionCreate,
    user: User,
) -> Execution:
    _require_project_write(session, user, project_id)

    test: SecurityTest | None = None
    if payload.test_id is not None:
        test = session.get(SecurityTest, payload.test_id)
        if test is None or test.project_id != project_id:
            raise AssessmentNotFoundError()

    target: Target | None = None
    if payload.target_id is not None:
        target = _require_project_target(session, project_id, payload.target_id)

    # Provider, target status, and capabilities are checked together so an
    # execution cannot be created against a pairing that cannot run.
    validate_execution_binding(test, target)

    execution = Execution(
        project_id=project_id,
        test_id=payload.test_id,
        target_id=payload.target_id,
        status=ExecutionStatus.PENDING,
        created_by=user.id,
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)
    record_audit_event(
        session,
        actor_id=user.id,
        action="execution.created",
        resource_type="execution",
        resource_id=str(execution.id),
        event_metadata={"project_id": str(project_id)},
    )
    return execution


def get_execution(session: Session, execution_id: UUID, user: User) -> Execution:
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise AssessmentNotFoundError()
    _require_project(session, user, execution.project_id)
    return execution


def delete_execution(session: Session, execution_id: UUID, user: User) -> None:
    """Delete a single execution and its findings, steps, and evidence.

    Allows removing an individual executed test log rather than the entire
    project history. Test definitions and reports are untouched.
    """

    execution = get_execution(session, execution_id, user)
    _require_project_write(session, user, execution.project_id)

    session.execute(delete(ExecutionStep).where(ExecutionStep.execution_id == execution_id))
    session.execute(delete(Finding).where(Finding.execution_id == execution_id))
    session.delete(execution)
    session.commit()
    record_audit_event(
        session,
        actor_id=user.id,
        action="execution.deleted",
        resource_type="execution",
        resource_id=str(execution_id),
        event_metadata={"project_id": str(execution.project_id)},
    )


def list_executions(session: Session, project_id: UUID, user: User) -> list[Execution]:
    _require_project(session, user, project_id)
    return list(
        session.scalars(
            select(Execution)
            .where(Execution.project_id == project_id)
            .order_by(Execution.created_at, Execution.id)
        ).all()
    )


def first_findings_by_execution(session: Session, execution_ids: list[UUID]) -> dict[UUID, Finding]:
    """Return the finding that best explains each execution's result.

    The executions list shows why a test failed. Infrastructure failures carry
    their reason in ``Execution.error``; an attack that landed carries it in
    the finding its grader produced. Fetching them for a whole page in one
    query keeps the list cheap to poll.

    A confirmed finding outranks a candidate, which outranks a dismissed one:
    the row should name the best reason the result is what it is, not the
    oldest finding that happens to exist.
    """

    if not execution_ids:
        return {}

    findings = session.scalars(
        select(Finding)
        .where(Finding.execution_id.in_(execution_ids))
        .order_by(Finding.created_at, Finding.id)
    ).all()

    preference = {
        FindingConfirmation.CONFIRMED: 0,
        FindingConfirmation.CANDIDATE: 1,
        FindingConfirmation.DISMISSED: 2,
    }
    first_by_execution: dict[UUID, Finding] = {}
    for finding in findings:
        if finding.execution_id is None:
            continue
        current = first_by_execution.get(finding.execution_id)
        if current is None:
            first_by_execution[finding.execution_id] = finding
        elif preference.get(finding.confirmation, 1) < preference.get(current.confirmation, 1):
            first_by_execution[finding.execution_id] = finding
    return first_by_execution


def create_finding(session: Session, payload: FindingCreate, user: User) -> Finding:
    execution = get_execution(session, payload.execution_id, user)
    _require_project_write(session, user, execution.project_id)
    finding = Finding(
        execution_id=execution.id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        details=payload.details,
    )
    # Apply automatic severity when the caller did not supply an explicit one.
    if finding.severity is None:
        finding.severity = compute_automatic_severity(finding)
    session.add(finding)
    session.commit()
    session.refresh(finding)
    return finding


def list_findings(session: Session, execution_id: UUID, user: User) -> list[Finding]:
    execution = get_execution(session, execution_id, user)
    return list(
        session.scalars(
            select(Finding).where(Finding.execution_id == execution.id).order_by(Finding.created_at)
        ).all()
    )


def update_finding(
    session: Session,
    finding_id: UUID,
    payload: FindingUpdate,
    user: User,
) -> Finding:
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise AssessmentNotFoundError()
    _require_project_write(session, user, _finding_project_id(session, finding))
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(finding, field, value)
    session.commit()
    session.refresh(finding)
    return finding


def create_evidence(session: Session, payload: EvidenceCreate, user: User) -> Evidence:
    finding = session.get(Finding, payload.finding_id)
    if finding is None:
        raise AssessmentNotFoundError()
    _require_project_write(session, user, _finding_project_id(session, finding))
    update_finding(
        session,
        payload.finding_id,
        FindingUpdate(status=FindingStatus.IN_PROGRESS),
        user,
    )
    evidence = Evidence(
        finding_id=payload.finding_id,
        kind=payload.kind,
        description=payload.description,
        content=payload.content,
    )
    session.add(evidence)
    session.commit()
    session.refresh(evidence)
    return evidence


def list_evidence(session: Session, finding_id: UUID, user: User) -> list[Evidence]:
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise AssessmentNotFoundError()
    _require_project(session, user, _finding_project_id(session, finding))
    return list(
        session.scalars(
            select(Evidence).where(Evidence.finding_id == finding_id).order_by(Evidence.created_at)
        ).all()
    )


def triage_finding(
    session: Session,
    project_id: UUID,
    finding_id: UUID,
    payload: FindingTriageRequest,
    user: User,
) -> Finding:
    """Apply a reviewer's confirmation decision to a finding.

    This is the human second stage of grading: the reviewer either confirms
    that the observed attack result is real, dismisses it as a false positive
    (with a reason), or returns it to candidate. The resulting state change
    re-derives the execution's verdict, because the verdict is a statement
    about confirmations, not about lexical matches.
    """

    finding = session.get(Finding, finding_id)
    if finding is None:
        raise AssessmentNotFoundError()
    finding_project_id = _finding_project_id(session, finding)
    if finding_project_id != project_id:
        raise AssessmentNotFoundError()
    _require_project_write(session, user, finding_project_id)
    execution = (
        session.get(Execution, finding.execution_id) if finding.execution_id is not None else None
    )

    # Raises ValueError for a dismissal (or severity change) without a
    # reason; the route maps that to 422.
    payload.require_reason(finding.severity)

    if payload.severity is not None:
        finding.severity = payload.severity
    apply_confirmation(
        [finding],
        payload.confirmation,
        source="human",
        reason=payload.reason,
        user_id=user.id,
    )
    if execution is not None:
        recompute_execution_result(session, execution)
    session.commit()
    session.refresh(finding)
    record_audit_event(
        session,
        actor_id=user.id,
        action="finding.triaged",
        resource_type="finding",
        resource_id=str(finding.id),
        event_metadata={
            "project_id": str(finding_project_id),
            "confirmation": payload.confirmation.value,
            "severity": finding.severity.value,
        },
    )
    return finding


def list_execution_steps(
    session: Session,
    project_id: UUID,
    execution_id: UUID,
    user: User,
) -> list[ExecutionStepResponse]:
    """Return the recorded transcript of an execution, redacted on read.

    Steps are stored verbatim so a run can always be reproduced and audited.
    The transcript endpoint must not become the one place a leaked credential
    is served in the clear, so every turn passes through the same detector
    used for stored evidence before it leaves the API.
    """

    execution = get_execution(session, execution_id, user)
    if execution.project_id != project_id:
        raise AssessmentNotFoundError()

    steps = session.scalars(
        select(ExecutionStep)
        .where(ExecutionStep.execution_id == execution_id)
        .order_by(ExecutionStep.turn_number)
    ).all()

    transcript: list[ExecutionStepResponse] = []
    for step in steps:
        redacted, detections, sensitivity = scan(
            {
                "request": step.request_content or {},
                "response": step.response_output,
            }
        )
        transcript.append(
            ExecutionStepResponse(
                id=step.id,
                execution_id=step.execution_id,
                turn_number=step.turn_number,
                request_content=redacted["request"],
                response_output=redacted["response"],
                status=step.status,
                error=step.error,
                created_at=step.created_at,
                redacted=len(detections) > 0,
                detected_kinds=sorted({detection.kind.value for detection in detections}),
                sensitivity=int(sensitivity),
            )
        )
    return transcript


def create_replay_execution(
    session: Session,
    project_id: UUID,
    execution_id: UUID,
    user: User,
) -> Execution:
    """Queue a fresh run of the same test against the same target.

    Replay exists so any result can be reproduced on demand: the transcript
    shows exactly what was sent, and this creates the execution that sends it
    again. The new run is independent — it records its own result, findings,
    and confirmation state — so replaying never overwrites history.
    """

    source = get_execution(session, execution_id, user)
    if source.project_id != project_id:
        raise AssessmentNotFoundError()
    _require_project_write(session, user, source.project_id)

    if source.test_id is None or source.target_id is None:
        raise ExecutionBindingError(
            "this execution has no test or target to replay; the source test or target was deleted"
        )

    test = session.get(SecurityTest, source.test_id)
    if test is None or test.project_id != project_id:
        raise AssessmentNotFoundError()
    target = _require_project_target(session, project_id, source.target_id)
    validate_execution_binding(test, target)

    execution = Execution(
        project_id=project_id,
        test_id=source.test_id,
        target_id=source.target_id,
        status=ExecutionStatus.PENDING,
        created_by=user.id,
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)
    record_audit_event(
        session,
        actor_id=user.id,
        action="execution.replayed",
        resource_type="execution",
        resource_id=str(execution.id),
        event_metadata={
            "project_id": str(project_id),
            "source_execution_id": str(source.id),
        },
    )
    return execution


def test_triage_stats(
    session: Session,
    project_id: UUID,
    user: User,
) -> list[TestTriageStats]:
    """Report per-test triage outcomes, worst signal first.

    This is the attack library's feedback loop: a test whose findings are
    consistently dismissed is producing noise, and its patterns need
    tightening rather than its coverage being celebrated. Computed from the
    findings themselves, so there is no counter that can drift out of sync.
    """

    _require_project(session, user, project_id)

    rows = session.execute(
        select(
            Execution.test_id,
            Finding.confirmation,
            func.count(Finding.id),
        )
        .join(Finding, Finding.execution_id == Execution.id)
        .where(
            Execution.project_id == project_id,
            Execution.test_id.is_not(None),
        )
        .group_by(Execution.test_id, Finding.confirmation)
    ).all()

    buckets: dict[UUID, dict[str, int]] = {}
    for test_id, confirmation, count in rows:
        if test_id is None:
            continue
        bucket = buckets.setdefault(
            test_id,
            {"findings": 0, "confirmed": 0, "candidate": 0, "dismissed": 0},
        )
        bucket["findings"] += count
        key = (
            confirmation.value
            if isinstance(confirmation, FindingConfirmation)
            else str(confirmation)
        )
        if key in bucket:
            bucket[key] += count

    if not buckets:
        return []

    tests = session.scalars(select(SecurityTest).where(SecurityTest.id.in_(list(buckets)))).all()

    stats: list[TestTriageStats] = []
    for test in tests:
        bucket = buckets.get(test.id)
        if bucket is None:
            continue
        config = test.config if isinstance(test.config, dict) else {}
        category = config.get("category")
        dismissed_rate = bucket["dismissed"] / bucket["findings"] if bucket["findings"] else 0.0
        stats.append(
            TestTriageStats(
                test_id=test.id,
                test_name=test.name,
                category=category if isinstance(category, str) else None,
                findings=bucket["findings"],
                confirmed=bucket["confirmed"],
                candidate=bucket["candidate"],
                dismissed=bucket["dismissed"],
                dismissed_rate=round(dismissed_rate, 4),
            )
        )

    stats.sort(key=lambda item: (-item.dismissed_rate, item.test_name))
    return stats


def create_report(
    session: Session,
    project_id: UUID,
    payload: ReportCreate,
    user: User,
) -> Report:
    _require_project_write(session, user, project_id)
    report = Report(
        project_id=project_id,
        title=payload.title,
        format=payload.format,
        path="",
        created_by=user.id,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    record_audit_event(
        session,
        actor_id=user.id,
        action="report.created",
        resource_type="report",
        resource_id=str(report.id),
        event_metadata={"project_id": str(project_id), "format": payload.format},
    )
    return report


def list_reports(session: Session, project_id: UUID, user: User) -> list[Report]:
    _require_project(session, user, project_id)
    return list(
        session.scalars(
            select(Report).where(Report.project_id == project_id).order_by(Report.created_at)
        ).all()
    )


def delete_execution_history(
    session: Session,
    project_id: UUID,
    user: User,
) -> int:
    """Delete all execution-run data for a project.

    Removes executions, execution steps, findings, and evidence. This is a
    destructive operation intended for clearing accumulated run data when a
    project is being reset or decommissioned. Test definitions and reports are
    left untouched.

    Returns the number of executions deleted.
    """

    _require_project_write(session, user, project_id)

    execution_ids = session.scalars(
        select(Execution.id).where(Execution.project_id == project_id)
    ).all()
    deleted = 0
    for execution_id in execution_ids:
        session.execute(delete(ExecutionStep).where(ExecutionStep.execution_id == execution_id))
        session.execute(delete(Finding).where(Finding.execution_id == execution_id))
        session.execute(delete(Execution).where(Execution.id == execution_id))
        deleted += 1

    if deleted:
        record_audit_event(
            session,
            actor_id=user.id,
            action="executions.bulk_deleted",
            resource_type="execution",
            resource_id=None,
            event_metadata={
                "project_id": str(project_id),
                "executions_deleted": deleted,
            },
        )
        session.commit()

    return deleted

"""Assessment (test, execution, finding, evidence, report) API routes for Aegis Vuldris."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.errors import ProjectNotFoundError
from app.db.session import get_db_session
from app.models.evidence import Sensitivity
from app.models.execution import Execution, ExecutionStatus
from app.models.finding import Finding
from app.schemas import (
    BulkExecutionAccepted,
    BulkExecutionCreate,
    EvidenceCreate,
    EvidenceResponse,
    ExecutionCreate,
    ExecutionFindingSummary,
    ExecutionResponse,
    ExecutionStepResponse,
    FindingCreate,
    FindingResponse,
    FindingTriageRequest,
    FindingUpdate,
    RemediationPlanResponse,
    ReportComparisonResponse,
    ReportCreate,
    ReportGenerateRequest,
    ReportResponse,
    SecurityTestCreate,
    SecurityTestResponse,
    SecurityTestUpdate,
    TestSeedRequest,
    TestSeedResponse,
    TestTriageStats,
    VerificationCreate,
)
from app.security.dependencies import CurrentUser
from app.services.assessments import (
    create_evidence,
    create_execution,
    create_finding,
    create_replay_execution,
    create_report,
    create_security_test,
    delete_execution,
    delete_execution_history,
    delete_security_test,
    first_findings_by_execution,
    get_execution,
    get_security_test,
    list_evidence,
    list_execution_steps,
    list_executions,
    list_findings,
    list_reports,
    list_security_tests,
    test_triage_stats,
    triage_finding,
    update_finding,
    update_security_test,
)
from app.services.audit import record_audit_event
from app.services.bulk_execution import (
    DEFAULT_BULK_CONCURRENCY,
    create_bulk_executions,
    run_bulk_executions,
)
from app.services.execution_engine import (
    cancel_execution,
    get_engine,
    start_execution,
)
from app.services.remediation import get_remediation_plan
from app.services.report_generation import (
    compare_reports,
    generate_report,
    get_report_download_path,
    require_project_report,
)
from app.services.seed_tests import seed_project_tests
from app.services.verification import (
    create_verification_execution,
    list_verifications,
)

router = APIRouter(
    prefix="/projects/{project_id}/assessments",
    tags=["assessments"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


def _test_response(test) -> SecurityTestResponse:
    return SecurityTestResponse.model_validate(test)


@router.post("/tests", response_model=SecurityTestResponse, status_code=status.HTTP_201_CREATED)
async def create_test_endpoint(
    project_id: UUID,
    payload: SecurityTestCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> SecurityTestResponse:
    return _test_response(create_security_test(session, project_id, payload, current_user))


@router.get("/tests", response_model=list[SecurityTestResponse])
async def list_tests_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[SecurityTestResponse]:
    return [_test_response(t) for t in list_security_tests(session, project_id, current_user)]


@router.get("/tests/triage-stats", response_model=list[TestTriageStats])
async def test_triage_stats_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[TestTriageStats]:
    """Per-test confirm/dismiss counts, worst dismissal rate first.

    The feedback loop for the attack library: a test whose findings are
    consistently dismissed is producing false positives, and its patterns
    should be tightened. Computed from the findings themselves, so there is
    no counter that can drift out of sync with the data.
    """

    return test_triage_stats(session, project_id, current_user)


@router.get("/tests/{test_id}", response_model=SecurityTestResponse)
async def get_test_endpoint(
    project_id: UUID,
    test_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> SecurityTestResponse:
    return _test_response(get_security_test(session, test_id, current_user))


@router.patch("/tests/{test_id}", response_model=SecurityTestResponse)
async def update_test_endpoint(
    project_id: UUID,
    test_id: UUID,
    payload: SecurityTestUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> SecurityTestResponse:
    _ = get_security_test(session, test_id, current_user)
    return _test_response(update_security_test(session, test_id, payload, current_user))


@router.post("/tests/seed", response_model=TestSeedResponse)
async def seed_tests_endpoint(
    project_id: UUID,
    payload: TestSeedRequest,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> TestSeedResponse:
    """Load the bundled security test library into a project.

    The YAML files under ``app/test_cases`` are static and are not imported
    automatically, so a new project has no tests until this is called. The
    operation is idempotent: tests already present in the project are skipped,
    so it is safe to call repeatedly.
    """

    report = seed_project_tests(
        session,
        project_id,
        current_user,
        categories=set(payload.category) or None,
    )
    return TestSeedResponse.from_report(report)


@router.delete("/tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test_endpoint(
    project_id: UUID,
    test_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> None:
    delete_security_test(session, test_id, current_user)


@router.delete("/executions/history", status_code=status.HTTP_200_OK)
async def delete_execution_history_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> dict[str, Any]:
    """Delete all past executions, findings, and evidence for a project.

    This clears accumulated run data while preserving test definitions and
    generated reports. Requires project write access.
    """

    deleted = delete_execution_history(session, project_id, current_user)
    msg = f"Deleted {deleted} execution(s) and associated findings and evidence."
    return {"deleted": deleted, "message": msg}


@router.post("/executions", response_model=ExecutionResponse, status_code=status.HTTP_201_CREATED)
async def create_execution_endpoint(
    project_id: UUID,
    payload: ExecutionCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ExecutionResponse:
    return ExecutionResponse.model_validate(
        create_execution(session, project_id, payload, current_user)
    )


@router.post(
    "/executions/bulk",
    response_model=BulkExecutionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_bulk_executions_endpoint(
    project_id: UUID,
    payload: BulkExecutionCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> BulkExecutionAccepted:
    """Queue one execution per selected test against a single target.

    Selecting and running tests one at a time is not a realistic workflow for
    a suite of 224. This creates every execution up front -- so a bad selection
    is rejected before anything runs -- then hands them to a bounded runner.

    Returns 202 rather than the result. A whole suite against a local model
    takes minutes and nginx caps a request at 300s, so awaiting the run here
    would truncate it mid-suite. Progress is read from the executions this
    project already exposes, keyed by ``test_id``.
    """

    created = create_bulk_executions(
        session,
        project_id,
        current_user,
        payload.test_ids,
        payload.target_id,
    )

    # Schedule only after every row exists, so a rejected selection never
    # leaves a half-created suite that a poller would read as "in progress".
    await run_bulk_executions(
        get_engine(),
        [execution.id for execution in created],
        concurrency=DEFAULT_BULK_CONCURRENCY,
    )

    return BulkExecutionAccepted(
        total=len(created),
        target_id=payload.target_id,
        execution_ids=[execution.id for execution in created],
    )


def _execution_response(execution: Execution, finding: Finding | None = None) -> ExecutionResponse:
    """Serialize an execution, including why it reads the way it does.

    Infrastructure failures carry their reason in ``error``; an attack that
    landed carries it in the finding its grader produced. The executions table
    shows both, so both travel in the payload.
    """

    response = ExecutionResponse.model_validate(execution)
    if finding is not None:
        response.finding_summary = ExecutionFindingSummary.model_validate(finding)
    return response


@router.get("/executions", response_model=list[ExecutionResponse])
async def list_executions_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[ExecutionResponse]:
    executions = list_executions(session, project_id, current_user)
    findings = first_findings_by_execution(session, [execution.id for execution in executions])
    return [_execution_response(execution, findings.get(execution.id)) for execution in executions]


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution_endpoint(
    project_id: UUID,
    execution_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ExecutionResponse:
    """Return a single execution for status polling."""

    execution = get_execution(session, execution_id, current_user)
    if execution.project_id != project_id:
        raise ProjectNotFoundError()

    finding = first_findings_by_execution(session, [execution.id]).get(execution.id)
    return _execution_response(execution, finding)


@router.post(
    "/executions/{execution_id}/run",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_execution_endpoint(
    project_id: UUID,
    execution_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ExecutionResponse:
    """Queue an execution for background processing.

    Returns 202 Accepted with the execution record. The execution transitions
    from PENDING to RUNNING asynchronously; poll GET /executions/{id} for
    status.
    """

    execution = get_execution(session, execution_id, current_user)
    if execution.project_id != project_id:
        raise ProjectNotFoundError()

    if execution.status != ExecutionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"execution is in '{execution.status.value}' state; "
                "only PENDING executions can be started."
            ),
        )

    start_execution(execution.id)

    return ExecutionResponse.model_validate(execution)


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionResponse,
)
async def cancel_execution_endpoint(
    project_id: UUID,
    execution_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ExecutionResponse:
    """Attempt to cancel a running or pending execution."""

    execution = get_execution(session, execution_id, current_user)
    if execution.project_id != project_id:
        raise ProjectNotFoundError()

    cancelled = cancel_execution(execution.id)

    session.refresh(execution)

    if not cancelled:
        return ExecutionResponse.model_validate(execution)

    return ExecutionResponse.model_validate(execution)


@router.delete(
    "/executions/{execution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_execution_endpoint(
    project_id: UUID,
    execution_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> None:
    """Delete a single executed test log and its findings/evidence."""

    execution = get_execution(session, execution_id, current_user)
    if execution.project_id != project_id:
        raise ProjectNotFoundError()
    delete_execution(session, execution_id, current_user)


@router.get(
    "/executions/{execution_id}/steps",
    response_model=list[ExecutionStepResponse],
)
async def list_execution_steps_endpoint(
    project_id: UUID,
    execution_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[ExecutionStepResponse]:
    """Return the recorded transcript of a run: one entry per turn.

    Each entry carries the exact request content (messages, model,
    parameters, converters applied) and the response the target returned,
    redacted on read with the same detector used for stored evidence.
    ``redacted`` and ``detected_kinds`` report what was replaced so the
    caller can tell a clean transcript from one where a secret was found.
    """

    transcript = list_execution_steps(session, project_id, execution_id, current_user)
    record_audit_event(
        session,
        actor_id=current_user.id,
        action="execution.transcript_viewed",
        resource_type="execution",
        resource_id=str(execution_id),
        event_metadata={"project_id": str(project_id), "steps": len(transcript)},
    )
    return transcript


@router.post(
    "/executions/{execution_id}/replay",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replay_execution_endpoint(
    project_id: UUID,
    execution_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ExecutionResponse:
    """Queue a fresh run of the same test and target as an existing run.

    Replay never overwrites the source run: it creates a new execution that
    records its own result, findings, and confirmation state. Use it to
    reproduce a result on demand or to re-check a target after a change.
    """

    execution = create_replay_execution(session, project_id, execution_id, current_user)
    start_execution(execution.id)
    return ExecutionResponse.model_validate(execution)


@router.post("/findings", response_model=FindingResponse, status_code=status.HTTP_201_CREATED)
async def create_finding_endpoint(
    payload: FindingCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> FindingResponse:
    return FindingResponse.model_validate(create_finding(session, payload, current_user))


@router.get("/executions/{execution_id}/findings", response_model=list[FindingResponse])
async def list_findings_endpoint(
    project_id: UUID,
    execution_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[FindingResponse]:
    return [
        FindingResponse.model_validate(f)
        for f in list_findings(session, execution_id, current_user)
    ]


@router.patch("/findings/{finding_id}", response_model=FindingResponse)
async def update_finding_endpoint(
    project_id: UUID,
    finding_id: UUID,
    payload: FindingUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> FindingResponse:
    return FindingResponse.model_validate(
        update_finding(session, finding_id, payload, current_user)
    )


@router.post("/findings/{finding_id}/triage", response_model=FindingResponse)
async def triage_finding_endpoint(
    project_id: UUID,
    finding_id: UUID,
    payload: FindingTriageRequest,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> FindingResponse:
    """Apply a reviewer's confirmation decision to a finding.

    This is the human second stage of grading. Confirming or dismissing a
    finding re-derives the execution's result: the run becomes ``fail`` once
    something is confirmed, and ``pass`` once every observed match has been
    dismissed as a false positive. A dismissal must carry a reason.
    """

    try:
        finding = triage_finding(session, project_id, finding_id, payload, current_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return FindingResponse.model_validate(finding)


@router.get("/findings/{finding_id}/remediation", response_model=RemediationPlanResponse)
async def get_remediation_endpoint(
    project_id: UUID,
    finding_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> RemediationPlanResponse:
    """Return a review-only, deterministic AutoFix plan for one finding.

    This endpoint intentionally does not call a model, read source files, or
    apply a patch. It is Level 1 (Suggest): a human must review the proposed
    controls and the verification plan before any remediation action.
    """

    plan = get_remediation_plan(session, project_id, finding_id, current_user)
    record_audit_event(
        session,
        actor_id=current_user.id,
        action="remediation.viewed",
        resource_type="finding",
        resource_id=str(finding_id),
        event_metadata={
            "project_id": str(project_id),
            "kind": plan.kind,
            "template_version": plan.template_version,
        },
    )
    return RemediationPlanResponse.model_validate(plan)


@router.post(
    "/findings/{finding_id}/verifications",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_verification_endpoint(
    project_id: UUID,
    finding_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    payload: VerificationCreate | None = None,
) -> ExecutionResponse:
    """Queue a deterministic re-run of the exact attack behind a finding.

    Only a finding marked ``fixed`` can be verified, and only a passed re-run
    moves it to ``verified``. This endpoint applies nothing: it re-runs the
    attack that produced the finding and records what happens.
    """

    execution = create_verification_execution(
        session,
        project_id,
        finding_id,
        payload if payload is not None else VerificationCreate(),
        current_user,
    )
    start_execution(execution.id)
    return ExecutionResponse.model_validate(execution)


@router.get(
    "/findings/{finding_id}/verifications",
    response_model=list[ExecutionResponse],
)
async def list_verifications_endpoint(
    project_id: UUID,
    finding_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[ExecutionResponse]:
    """List the verification runs for a finding, oldest first."""

    return [
        ExecutionResponse.model_validate(execution)
        for execution in list_verifications(session, project_id, finding_id, current_user)
    ]


@router.post("/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def create_evidence_endpoint(
    payload: EvidenceCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> EvidenceResponse:
    return EvidenceResponse.model_validate(create_evidence(session, payload, current_user))


@router.get("/findings/{finding_id}/evidence", response_model=list[EvidenceResponse])
async def list_evidence_endpoint(
    project_id: UUID,
    finding_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[EvidenceResponse]:
    """List evidence for a finding.

    Audited because evidence is the most sensitive data Aegis Vuldris holds: it
    contains the prompts sent and the model's responses, including whatever the
    model was induced to disclose.
    """

    records = list_evidence(session, finding_id, current_user)

    record_audit_event(
        session,
        actor_id=current_user.id,
        action="evidence.viewed",
        resource_type="finding",
        resource_id=str(finding_id),
        event_metadata={
            "project_id": str(project_id),
            # Counts only. Evidence content is never placed in an audit entry.
            "record_count": len(records),
            "restricted_count": sum(
                1 for record in records if record.sensitivity >= int(Sensitivity.RESTRICTED)
            ),
        },
    )

    return [EvidenceResponse.model_validate(record) for record in records]


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report_endpoint(
    project_id: UUID,
    payload: ReportCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ReportResponse:
    return ReportResponse.model_validate(create_report(session, project_id, payload, current_user))


@router.post(
    "/reports/{report_id}/generate",
    response_model=ReportResponse,
)
async def generate_report_endpoint(
    project_id: UUID,
    report_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    payload: ReportGenerateRequest | None = None,
) -> ReportResponse:
    """Generate (or regenerate) a report artifact and return its updated record.

    With ``baseline_report_id`` the artifact embeds a "changes since baseline"
    section. The baseline must belong to the same project, and passes the
    same caller authorization as the report being generated.
    """

    report = require_project_report(session, current_user, project_id, report_id)
    baseline_report_id: UUID | None = None
    if payload is not None and payload.baseline_report_id is not None:
        baseline = require_project_report(
            session, current_user, project_id, payload.baseline_report_id
        )
        baseline_report_id = baseline.id
    generate_report(session, report, baseline_report_id=baseline_report_id)
    session.refresh(report)
    record_audit_event(
        session,
        actor_id=current_user.id,
        action="report.generated",
        resource_type="report",
        resource_id=str(report.id),
        event_metadata={
            "project_id": str(project_id),
            "format": report.format,
            **({"baseline_report_id": str(baseline_report_id)} if baseline_report_id else {}),
        },
    )
    return ReportResponse.model_validate(report)


@router.get("/reports", response_model=list[ReportResponse])
async def list_reports_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[ReportResponse]:
    """List report history for a project, oldest version first."""

    return [
        ReportResponse.model_validate(r) for r in list_reports(session, project_id, current_user)
    ]


@router.get("/reports/{report_id}/download")
async def download_report_endpoint(
    project_id: UUID,
    report_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> FileResponse:
    """Download a generated report artifact.

    Report artifacts contain the full evidence set, so the response is marked
    no-store to keep them out of shared and browser caches.
    """

    require_project_report(session, current_user, project_id, report_id)
    path = get_report_download_path(session, report_id, project_id)
    record_audit_event(
        session,
        actor_id=current_user.id,
        action="report.downloaded",
        resource_type="report",
        resource_id=str(report_id),
        event_metadata={"project_id": str(project_id)},
    )
    media_type = "application/json" if path.suffix == ".json" else "text/markdown"
    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=path.name,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/reports/{report_a_id}/compare/{report_b_id}",
    response_model=ReportComparisonResponse,
)
async def compare_reports_endpoint(
    project_id: UUID,
    report_a_id: UUID,
    report_b_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ReportComparisonResponse:
    """Compare two report runs and return new/resolved/regressed findings."""

    # Both reports must be authorized against the same project, otherwise a
    # caller could compare their own report against another tenant's.
    require_project_report(session, current_user, project_id, report_a_id)
    require_project_report(session, current_user, project_id, report_b_id)
    record_audit_event(
        session,
        actor_id=current_user.id,
        action="report.compared",
        resource_type="report",
        resource_id=str(report_a_id),
        event_metadata={
            "project_id": str(project_id),
            "other_report_id": str(report_b_id),
        },
    )
    return ReportComparisonResponse.model_validate(
        compare_reports(session, report_a_id, report_b_id, project_id)
    )

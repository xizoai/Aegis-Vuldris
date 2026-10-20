"""Deterministic fix verification for findings.

Applying a fix is a human decision; verifying one is not. A verification run
re-executes the exact security test that produced a finding and records what
happened. Only a passed rerun moves the finding to ``verified`` -- never a
generated suggestion, a model's claim, or a status edited by hand.

The verdict is a statement about an execution, not about the world: "this
attack, on this target, no longer reproduces". The re-run uses the test
definition as it exists at verification time, and the audit trail records
which attack, version, and target were used.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import (
    AssessmentNotFoundError,
    ExecutionBindingError,
    ProjectNotFoundError,
)
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.finding import Finding, FindingStatus
from app.models.project import Project
from app.models.target import Target
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas import VerificationCreate
from app.services.assessments import get_execution, validate_execution_binding
from app.services.audit import record_audit_event
from app.services.projects import ensure_project_access

# A passed rerun is a rerun that succeeded without re-producing the finding.
# INCONCLUSIVE is deliberately not "passed": an unproven fix is not a
# verified one, and NO_FINDINGS is a success with nothing to report.
_PASSED_RESULTS = {ExecutionResult.PASS, ExecutionResult.NO_FINDINGS}


def _attack_metadata(test: SecurityTest) -> dict[str, str]:
    """Return the attack identity this test carries, when it carries one."""

    config = test.config if isinstance(test.config, dict) else {}
    attack = config.get("attack")
    if not isinstance(attack, dict):
        return {}
    metadata: dict[str, str] = {}
    if isinstance(attack.get("id"), str):
        metadata["attack_id"] = attack["id"]
    if isinstance(attack.get("version"), str):
        metadata["attack_version"] = attack["version"]
    return metadata


def _load_source(
    session: Session, project_id: UUID, finding_id: UUID, user: User
) -> tuple[Finding, Execution]:
    """Load a finding and authorize its reading, paired with the project."""

    finding = session.get(Finding, finding_id)
    if finding is None:
        raise AssessmentNotFoundError()
    if finding.execution_id is None:
        # An external scan finding has no execution transcript to replay.
        raise AssessmentNotFoundError()
    source = get_execution(session, finding.execution_id, user)
    if source.project_id != project_id:
        raise ProjectNotFoundError()
    return finding, source


def create_verification_execution(
    session: Session,
    project_id: UUID,
    finding_id: UUID,
    payload: VerificationCreate,
    user: User,
) -> Execution:
    """Create the re-run for a fixed finding, ready to be started.

    The execution re-uses the security test that produced the finding, so the
    attack is identical, and by default the original target. A different
    target in the same project can be named explicitly.
    """

    finding, source = _load_source(session, project_id, finding_id, user)
    _require_project_write(session, project_id, user)

    if finding.status != FindingStatus.FIXED:
        raise ExecutionBindingError(
            f"finding status is {finding.status.value!r}; only a finding marked "
            "'fixed' (the applied state) can be verified"
        )

    in_flight = session.scalar(
        select(Execution.id).where(
            Execution.verifies_finding_id == finding.id,
            Execution.status.in_([ExecutionStatus.PENDING, ExecutionStatus.RUNNING]),
        )
    )
    if in_flight is not None:
        raise ExecutionBindingError("a verification run for this finding is already in progress")

    test = session.get(SecurityTest, source.test_id) if source.test_id else None
    if test is None:
        raise ExecutionBindingError(
            "the security test that produced this finding was deleted; "
            "the exact attack cannot be re-run"
        )

    if payload.target_id is not None:
        target = session.get(Target, payload.target_id)
        if target is None or target.project_id != project_id:
            raise AssessmentNotFoundError()
    else:
        target = session.get(Target, source.target_id) if source.target_id else None
        if target is None or target.project_id != project_id:
            raise ExecutionBindingError(
                "the original target was deleted; choose a target to verify against"
            )

    validate_execution_binding(test, target)

    execution = Execution(
        project_id=project_id,
        test_id=test.id,
        target_id=target.id,
        status=ExecutionStatus.PENDING,
        created_by=user.id,
        verifies_finding_id=finding.id,
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)

    record_audit_event(
        session,
        actor_id=user.id,
        action="verification.requested",
        resource_type="finding",
        resource_id=str(finding.id),
        event_metadata={
            "project_id": str(project_id),
            "execution_id": str(execution.id),
            "test_id": str(test.id),
            "target_id": str(target.id),
            **_attack_metadata(test),
        },
    )
    return execution


def list_verifications(
    session: Session, project_id: UUID, finding_id: UUID, user: User
) -> list[Execution]:
    """List the verification runs for a finding, oldest first."""

    _load_source(session, project_id, finding_id, user)
    return list(
        session.scalars(
            select(Execution)
            .where(Execution.verifies_finding_id == finding_id)
            .order_by(Execution.created_at, Execution.id)
        ).all()
    )


def record_verification_outcome(session: Session, execution: Execution) -> str | None:
    """Record the verdict of a finished verification run, if it has one.

    Called by the execution engine after a run reaches a terminal state.
    Returns ``passed``/``failed``/``inconclusive``, or ``None`` when the
    execution is not a verification run or produced no verdict.

    Only a passed verdict on a finding still marked ``fixed`` moves it to
    ``verified``; every verdict is audited either way.
    """

    if execution.verifies_finding_id is None:
        return None
    if execution.status != ExecutionStatus.SUCCEEDED:
        return None

    finding = session.get(Finding, execution.verifies_finding_id)
    if finding is None:
        return None

    if execution.result in _PASSED_RESULTS:
        verdict = "passed"
        action = "finding.verification_passed"
        if finding.status == FindingStatus.FIXED:
            finding.status = FindingStatus.VERIFIED
    elif execution.result == ExecutionResult.FAIL:
        verdict = "failed"
        action = "finding.verification_failed"
    else:
        verdict = "inconclusive"
        action = "finding.verification_inconclusive"

    record_audit_event(
        session,
        actor_id=execution.created_by,
        action=action,
        resource_type="finding",
        resource_id=str(finding.id),
        event_metadata={
            "project_id": str(execution.project_id),
            "execution_id": str(execution.id),
            "result": execution.result.value,
            "finding_status": finding.status.value,
        },
    )
    session.commit()
    return verdict


def _require_project_write(session: Session, project_id: UUID, user: User) -> None:
    """Authorize a state-changing operation on a project."""

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "update")


__all__ = [
    "create_verification_execution",
    "list_verifications",
    "record_verification_outcome",
]

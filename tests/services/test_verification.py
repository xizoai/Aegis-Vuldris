"""Fix verification loop service tests.

A verification run re-executes the exact attack that produced a finding.
Only a passed rerun may move a finding to ``verified``, the API refuses to
set that state by hand, and every verdict is audited with the execution
that produced it. These tests pin those honesty invariants.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.api.errors import (
    AssessmentNotFoundError,
    ExecutionBindingError,
    PermissionDeniedError,
    ProjectNotFoundError,
)
from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.finding import Finding, FindingStatus
from app.models.project import Project
from app.models.target import Target, TargetProvider
from app.models.test import SecurityTest
from app.models.user import User, UserRole
from app.schemas import (
    ExecutionCreate,
    FindingCreate,
    FindingUpdate,
    ProjectCreate,
    ProjectMembershipCreate,
    SecurityTestCreate,
    TargetCreate,
    UserCreate,
    VerificationCreate,
)
from app.services.assessments import (
    create_execution,
    create_finding,
    create_security_test,
    update_finding,
)
from app.services.auth import register_user
from app.services.memberships import create_project_membership
from app.services.projects import create_project
from app.services.targets import create_target
from app.services.verification import (
    create_verification_execution,
    list_verifications,
    record_verification_outcome,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

ATTACK = {
    "id": "builtin/jailbreak/01-classic-dan-jailbreak",
    "version": "1.0.0",
}


def _session() -> Session:
    return create_session_factory()()


def _register_user(session: Session, role: UserRole = UserRole.USER) -> User:
    user = register_user(
        session,
        UserCreate(
            email=f"verification-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )
    if role != UserRole.USER:
        user.role = role
        session.commit()
        session.refresh(user)
    return user


def _create_project(session: Session, owner: User) -> Project:
    return create_project(
        session,
        ProjectCreate(name=f"Verification Project {uuid4()}"),
        owner_id=owner.id,
    )


def _create_target(session: Session, project_id, owner: User) -> Target:
    return create_target(
        session,
        TargetCreate(
            project_id=project_id,
            name=f"Target {uuid4()}",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="test-model",
            capabilities=["chat"],
            timeout_seconds=30.0,
            authorization_attestation=True,
        ),
        project_id,
        owner,
    )


def _seed_finding(
    session: Session,
    *,
    status: FindingStatus | None = None,
) -> tuple[User, Project, Target, SecurityTest, Execution, Finding]:
    """Create a project, target, test, execution, and finding.

    Returns ``(owner, project, target, test, execution, finding)``. When
    ``status`` is given the finding is moved there through the update
    service, the same path the API uses.
    """

    owner = _register_user(session)
    project = _create_project(session, owner)
    target = _create_target(session, project.id, owner)
    test = create_security_test(
        session,
        project.id,
        SecurityTestCreate(
            name=f"Verification case {uuid4()}",
            provider="openai_compatible",
            config={"category": "jailbreak", "attack": dict(ATTACK)},
        ),
        owner,
    )
    execution = create_execution(
        session,
        project.id,
        ExecutionCreate(test_id=test.id, target_id=target.id),
        owner,
    )
    finding = create_finding(
        session,
        FindingCreate(execution_id=execution.id, title="Jailbreak bypass"),
        owner,
    )
    if status is not None:
        finding = update_finding(
            session,
            finding.id,
            FindingUpdate(status=status),
            owner,
        )
    return owner, project, target, test, execution, finding


def _complete(
    session: Session,
    execution: Execution,
    result: ExecutionResult,
) -> None:
    """Simulate the engine finishing a verification run with a verdict."""

    execution.status = ExecutionStatus.SUCCEEDED
    execution.result = result
    execution.completed_at = datetime.now(UTC)
    session.commit()


def _audit(session: Session, action: str, finding_id) -> AuditLog | None:
    return session.scalar(
        select(AuditLog).where(
            AuditLog.action == action,
            AuditLog.resource_id == str(finding_id),
        )
    )


def test_creates_a_run_reusing_the_exact_test_and_target() -> None:
    """The rerun must be the same attack on the same target by default."""

    session = _session()
    owner, project, target, test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )

        assert verification.verifies_finding_id == finding.id
        assert verification.test_id == test.id
        assert verification.target_id == target.id
        assert verification.status == ExecutionStatus.PENDING
        assert verification.created_by == owner.id
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_requesting_a_verification_is_audited_with_the_attack_identity() -> None:
    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )

        audit = _audit(session, "verification.requested", finding.id)
        assert audit is not None, "verification request was not audited"
        assert audit.actor_id == owner.id
        assert audit.event_metadata is not None
        assert audit.event_metadata["project_id"] == str(project.id)
        assert audit.event_metadata["execution_id"] == str(verification.id)
        assert audit.event_metadata["attack_id"] == ATTACK["id"]
        assert audit.event_metadata["attack_version"] == ATTACK["version"]
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_a_named_target_overrides_the_original() -> None:
    """Verifying against a fixed staging deployment is the point of the loop."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        staging = _create_target(session, project.id, owner)
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(target_id=staging.id), owner
        )

        assert verification.target_id == staging.id
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_only_a_fixed_finding_can_be_verified() -> None:
    """There is nothing to verify until someone claims a fix was applied."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(session)

    try:
        with pytest.raises(ExecutionBindingError):
            create_verification_execution(
                session, project.id, finding.id, VerificationCreate(), owner
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_a_second_run_while_one_is_in_flight_is_rejected() -> None:
    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        first = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        with pytest.raises(ExecutionBindingError):
            create_verification_execution(
                session, project.id, finding.id, VerificationCreate(), owner
            )

        # Once the run is terminal a re-verification is allowed again.
        first.status = ExecutionStatus.FAILED
        session.commit()
        second = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        assert second.id != first.id
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_deleted_test_cannot_be_verified() -> None:
    """Without the exact test there is no exact attack to re-run."""

    session = _session()
    owner, project, _target, test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        session.delete(test)
        session.commit()

        with pytest.raises(ExecutionBindingError):
            create_verification_execution(
                session, project.id, finding.id, VerificationCreate(), owner
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_deleted_target_cannot_be_verified_without_a_replacement() -> None:
    session = _session()
    owner, project, target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        session.delete(target)
        session.commit()

        with pytest.raises(ExecutionBindingError):
            create_verification_execution(
                session, project.id, finding.id, VerificationCreate(), owner
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_viewer_cannot_request_a_verification() -> None:
    """Running an attack is a write, even for a read-only member."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )
    viewer = _register_user(session)

    try:
        create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=viewer.id, role=UserRole.VIEWER),
            owner,
        )

        with pytest.raises(PermissionDeniedError):
            create_verification_execution(
                session, project.id, finding.id, VerificationCreate(), viewer
            )

        # Reading the history stays available to a viewer.
        assert list_verifications(session, project.id, finding.id, viewer) == []
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_stranger_is_denied() -> None:
    session = _session()
    _owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )
    stranger = _register_user(session)

    try:
        with pytest.raises(PermissionDeniedError):
            create_verification_execution(
                session, project.id, finding.id, VerificationCreate(), stranger
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_finding_paired_with_the_wrong_project_is_not_found() -> None:
    session = _session()
    owner, project_a, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )
    project_b = _create_project(session, owner)

    try:
        with pytest.raises(ProjectNotFoundError):
            create_verification_execution(
                session, project_b.id, finding.id, VerificationCreate(), owner
            )
    finally:
        session.delete(project_b)
        session.delete(project_a)
        session.commit()
        session.close()


def test_missing_finding_is_not_found() -> None:
    session = _session()
    owner, project, _target, _test, _execution, _finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        with pytest.raises(AssessmentNotFoundError):
            create_verification_execution(session, project.id, uuid4(), VerificationCreate(), owner)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_listing_returns_runs_oldest_first() -> None:
    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        first = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        first.status = ExecutionStatus.FAILED
        session.commit()
        second = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )

        runs = list_verifications(session, project.id, finding.id, owner)

        assert [run.id for run in runs] == [first.id, second.id]
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_passed_verdict_marks_a_fixed_finding_verified() -> None:
    """The re-run no longer reproduces the attack: that is the whole proof."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        _complete(session, verification, ExecutionResult.PASS)

        verdict = record_verification_outcome(session, verification)

        assert verdict == "passed"
        session.refresh(finding)
        assert finding.status == FindingStatus.VERIFIED

        audit = _audit(session, "finding.verification_passed", finding.id)
        assert audit is not None, "passed verdict was not audited"
        assert audit.event_metadata is not None
        assert audit.event_metadata["execution_id"] == str(verification.id)
        assert audit.event_metadata["finding_status"] == "verified"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_failed_verdict_leaves_the_finding_fixed() -> None:
    """A re-run that still triggers the finding must not be launderable."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        _complete(session, verification, ExecutionResult.FAIL)

        verdict = record_verification_outcome(session, verification)

        assert verdict == "failed"
        session.refresh(finding)
        assert finding.status == FindingStatus.FIXED
        assert _audit(session, "finding.verification_failed", finding.id) is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_inconclusive_verdict_is_not_a_pass() -> None:
    """An unproven fix is not a verified one."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        _complete(session, verification, ExecutionResult.INCONCLUSIVE)

        verdict = record_verification_outcome(session, verification)

        assert verdict == "inconclusive"
        session.refresh(finding)
        assert finding.status == FindingStatus.FIXED
        assert _audit(session, "finding.verification_inconclusive", finding.id) is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_passed_verdict_does_not_overwrite_a_later_human_status() -> None:
    """If the finding moved on while the run finished, the verdict records
    evidence but does not resurrect it as verified."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        update_finding(
            session,
            finding.id,
            FindingUpdate(status=FindingStatus.WONT_FIX),
            owner,
        )
        _complete(session, verification, ExecutionResult.PASS)

        verdict = record_verification_outcome(session, verification)

        assert verdict == "passed"
        session.refresh(finding)
        assert finding.status == FindingStatus.WONT_FIX
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_unfinished_or_foreign_runs_have_no_verdict() -> None:
    session = _session()
    owner, project, _target, _test, execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        # The original execution is not a verification run.
        execution.status = ExecutionStatus.SUCCEEDED
        execution.result = ExecutionResult.PASS
        session.commit()
        assert record_verification_outcome(session, execution) is None

        # A verification that has not finished yet has no verdict either.
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        verification.status = ExecutionStatus.RUNNING
        session.commit()
        assert record_verification_outcome(session, verification) is None

        session.refresh(finding)
        assert finding.status == FindingStatus.FIXED
        assert _audit(session, "finding.verification_passed", finding.id) is None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_deleting_the_finding_clears_the_link_without_blocking() -> None:
    """Deleting the finding removes the verdict target, not the audit trail."""

    session = _session()
    owner, project, _target, _test, _execution, finding = _seed_finding(
        session, status=FindingStatus.FIXED
    )

    try:
        verification = create_verification_execution(
            session, project.id, finding.id, VerificationCreate(), owner
        )
        verification_id = verification.id

        session.delete(finding)
        session.commit()

        reloaded = session.get(Execution, verification_id)
        assert reloaded is not None
        # expire_on_commit is off, so the session still holds the old link.
        session.refresh(reloaded)
        assert reloaded.verifies_finding_id is None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_verified_status_cannot_be_set_by_hand() -> None:
    """Editing a finding must never be able to claim a proof that never ran."""

    with pytest.raises(ValidationError):
        FindingUpdate(status=FindingStatus.VERIFIED)

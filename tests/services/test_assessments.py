"""Assessment service tests for Aegis Vuldris."""

from uuid import uuid4

import pytest
from app.api.errors import AssessmentNotFoundError, PermissionDeniedError
from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.execution import Execution, ExecutionStatus
from app.models.execution_step import ExecutionStep
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.project import Project
from app.models.report import Report
from app.models.user import User, UserRole
from app.schemas import (
    EvidenceCreate,
    ExecutionCreate,
    ExecutionUpdate,
    FindingCreate,
    FindingUpdate,
    ProjectCreate,
    ProjectMembershipCreate,
    ReportCreate,
    SecurityTestCreate,
    SecurityTestUpdate,
    UserCreate,
)
from app.services.assessments import (
    create_evidence,
    create_execution,
    create_finding,
    create_report,
    create_security_test,
    delete_execution_history,
    get_execution,
    list_executions,
    list_findings,
    list_security_tests,
    update_finding,
    update_security_test,
)
from app.services.auth import register_user
from app.services.memberships import create_project_membership
from app.services.projects import create_project
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session


def _session() -> Session:
    return create_session_factory()()


def _register_user(session: Session, role: UserRole = UserRole.USER) -> User:
    user = register_user(
        session,
        UserCreate(
            email=f"assessment-{uuid4()}@example.com",
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
        ProjectCreate(name=f"Assessment Project {uuid4()}"),
        owner_id=owner.id,
    )


def _create_test(session, project_id, user):
    return create_security_test(
        session,
        project_id,
        SecurityTestCreate(
            name="Prompt Injection Test",
            provider="openai_compatible",
            required_capabilities=["chat"],
        ),
        user,
    )


def test_owner_crud_security_test() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        test = _create_test(session, project.id, owner)
        updated = update_security_test(
            session,
            test.id,
            SecurityTestUpdate(name="Updated Test"),
            owner,
        )
        assert updated.name == "Updated Test"
        tests = list_security_tests(session, project.id, owner)
        assert test.id in {t.id for t in tests}
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_non_owner_cannot_create_test() -> None:
    session = _session()
    owner = _register_user(session)
    stranger = _register_user(session)
    project = _create_project(session, owner)

    try:
        with pytest.raises(PermissionDeniedError):
            create_security_test(
                session,
                project.id,
                SecurityTestCreate(name="X", provider="openai_compatible"),
                stranger,
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_member_can_read_project_tests() -> None:
    session = _session()
    owner = _register_user(session)
    member = _register_user(session)
    project = _create_project(session, owner)

    try:
        create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.VIEWER),
            owner,
        )
        assert list_security_tests(session, project.id, member) == []
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_execution_lifecycle_cannot_be_set_by_a_caller() -> None:
    """Status and result are engine-owned and must not be caller-settable.

    A caller that could write them could mark a failed run as succeeded/pass
    and hide a real finding, so the public update surface is empty.
    """

    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)
    test = _create_test(session, project.id, owner)

    try:
        execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
        assert execution.status == ExecutionStatus.PENDING

        # The update schema accepts no fields, so there is nothing to write.
        assert ExecutionUpdate().model_dump(exclude_unset=True) == {}

        # Passing a lifecycle field is rejected outright.
        with pytest.raises(ValidationError):
            ExecutionUpdate.model_validate({"status": "running"})

        with pytest.raises(AssessmentNotFoundError):
            get_execution(session, uuid4(), owner)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_execution_requires_authorized_test() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        with pytest.raises(AssessmentNotFoundError):
            create_execution(session, project.id, ExecutionCreate(test_id=uuid4()), owner)
        assert list_executions(session, project.id, owner) == []
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_findings_and_evidence_lifecycle() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)
    test = _create_test(session, project.id, owner)

    try:
        execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
        finding = create_finding(
            session,
            FindingCreate(
                execution_id=execution.id,
                title="Prompt injection",
                severity=FindingSeverity.HIGH,
            ),
            owner,
        )
        evidence = create_evidence(
            session,
            EvidenceCreate(
                finding_id=finding.id,
                kind="prompt_output",
                content={"text": "injected"},
            ),
            owner,
        )
        assert evidence.content["text"] == "injected"
        findings = list_findings(session, execution.id, owner)
        assert finding.id in {f.id for f in findings}

        updated = update_finding(
            session, finding.id, FindingUpdate(status=FindingStatus.FIXED), owner
        )
        assert updated.status == FindingStatus.FIXED
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_create_report_records_audit() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)
    report: Report | None = None

    try:
        report = create_report(session, project.id, ReportCreate(title="Findings"), owner)
        assert report.title == "Findings"
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "report.created",
                AuditLog.resource_id == str(report.id),
            )
        )
        assert audit is not None
    finally:
        if report is not None:
            session.delete(report)
        session.delete(project)
        session.commit()
        session.close()


def test_delete_execution_history_removes_executions_findings_and_evidence() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)
    test = _create_test(session, project.id, owner)

    try:
        execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
        finding = create_finding(
            session,
            FindingCreate(
                execution_id=execution.id,
                title="Prompt injection",
                severity=FindingSeverity.HIGH,
            ),
            owner,
        )
        create_evidence(
            session,
            EvidenceCreate(
                finding_id=finding.id,
                kind="prompt_output",
                content={"text": "injected"},
            ),
            owner,
        )

        deleted = delete_execution_history(session, project.id, owner)
        assert deleted == 1

        assert session.get(Execution, execution.id) is None
        assert session.scalar(select(Finding).where(Finding.execution_id == execution.id)) is None
        assert (
            session.scalar(select(ExecutionStep).where(ExecutionStep.execution_id == execution.id))
            is None
        )

        # Audit log should record the bulk deletion.
        events = session.scalars(
            select(AuditLog).where(AuditLog.action == "executions.bulk_deleted")
        ).all()
        matching = [
            event
            for event in events
            if (event.event_metadata or {}).get("project_id") == str(project.id)
        ]
        assert matching, "audit log entry not found"
        audit = matching[-1]
        audit_metadata = audit.event_metadata
        assert audit_metadata is not None
        assert audit_metadata["executions_deleted"] == 1
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_delete_execution_history_preserves_test_definitions_and_reports() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        test = _create_test(session, project.id, owner)
        report = create_report(session, project.id, ReportCreate(title="My Report"), owner)

        execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
        delete_execution_history(session, project.id, owner)

        assert session.get(Execution, execution.id) is None
        assert session.get(Report, report.id) is not None
        tests = list_security_tests(session, project.id, owner)
        assert test.id in {t.id for t in tests}
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_delete_execution_history_requires_owner() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)
    stranger = _register_user(session)

    try:
        with pytest.raises(PermissionDeniedError):
            delete_execution_history(session, project.id, stranger)
    finally:
        session.delete(project)
        session.commit()
        session.close()

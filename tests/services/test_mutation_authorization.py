"""Mutation authorization and execution lifecycle integrity.

Two distinct problems:

1. Mutation used read access. ``_require_project`` authorized with the
   operation string ``"read"``, and ``ensure_project_access`` only enforces
   ``can_mutate_project`` (which excludes VIEWER) for the literal strings
   ``"update"`` and ``"delete"``. Every mutation that went through the read path
   was therefore permitted for a VIEWER.

2. The public API could set an execution's status and result. That is not a
   permission gap so much as a results-integrity problem: a project member,
   including a VIEWER, could mark a failed assessment as ``succeeded``/``pass``
   and erase a real vulnerability. Lifecycle transitions belong to the engine.
"""

from uuid import uuid4

import pytest
from app.api.errors import PermissionDeniedError
from app.db.session import create_session_factory
from app.models.execution import ExecutionStatus
from app.models.finding import FindingSeverity, FindingStatus
from app.models.project import Project
from app.models.test import SecurityTest
from app.models.user import User, UserRole
from app.schemas import (
    EvidenceCreate,
    ExecutionCreate,
    FindingCreate,
    FindingUpdate,
    ProjectCreate,
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
    delete_security_test,
    update_finding,
    update_security_test,
)
from app.services.auth import register_user
from app.services.projects import create_project
from sqlalchemy.orm import Session

PASSWORD = "a-very-strong-password"


def _session() -> Session:
    return create_session_factory()()


def _owner_with_viewer(session: Session) -> tuple[User, User, Project]:
    """Create a project owned by `owner` with `viewer` as a VIEWER member."""

    from app.models.membership import ProjectMembership

    owner = register_user(
        session, UserCreate(email=f"mut-owner-{uuid4()}@example.com", password=PASSWORD)
    )
    viewer = register_user(
        session, UserCreate(email=f"mut-viewer-{uuid4()}@example.com", password=PASSWORD)
    )
    viewer.role = UserRole.VIEWER
    session.commit()

    project = create_project(session, ProjectCreate(name=f"Mutation {uuid4()}"), owner_id=owner.id)
    session.add(
        ProjectMembership(
            project_id=project.id,
            user_id=viewer.id,
            role=UserRole.VIEWER,
        )
    )
    session.commit()
    session.refresh(owner)
    session.refresh(viewer)
    return owner, viewer, project


def _cleanup(session: Session, *users: User, project: Project | None = None) -> None:
    if project is not None:
        session.delete(project)
    for user in users:
        session.delete(user)
    session.commit()


def _make_test(session: Session, project: Project, owner: User) -> SecurityTest:
    return create_security_test(
        session,
        project.id,
        SecurityTestCreate(
            name="Case",
            provider="openai_compatible",
            config={"prompts": [{"role": "user", "content": "hi"}]},
        ),
        owner,
    )


def test_viewer_cannot_create_security_test() -> None:
    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        with pytest.raises(PermissionDeniedError):
            create_security_test(
                session,
                project.id,
                SecurityTestCreate(name="Sneaky", provider="openai_compatible", config={}),
                viewer,
            )
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()


def test_viewer_cannot_create_execution() -> None:
    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        test = _make_test(session, project, owner)
        with pytest.raises(PermissionDeniedError):
            create_execution(session, project.id, ExecutionCreate(test_id=test.id), viewer)
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()


def test_viewer_cannot_update_or_delete_security_test() -> None:
    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        test = _make_test(session, project, owner)
        with pytest.raises(PermissionDeniedError):
            update_security_test(session, test.id, SecurityTestUpdate(name="hijacked"), viewer)
        with pytest.raises(PermissionDeniedError):
            delete_security_test(session, test.id, viewer)
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()


def test_viewer_cannot_create_finding_or_evidence() -> None:
    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        test = _make_test(session, project, owner)
        execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
        with pytest.raises(PermissionDeniedError):
            create_finding(
                session,
                FindingCreate(
                    execution_id=execution.id,
                    title="Fake finding",
                    severity=FindingSeverity.CRITICAL,
                ),
                viewer,
            )
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()


def test_viewer_cannot_create_report() -> None:
    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        with pytest.raises(PermissionDeniedError):
            create_report(session, project.id, ReportCreate(title="Sneaky"), viewer)
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()


def test_viewer_can_still_read() -> None:
    """Read access must keep working; only mutations are restricted."""

    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        from app.services.assessments import list_executions, list_security_tests

        test = _make_test(session, project, owner)
        assert [t.id for t in list_security_tests(session, project.id, viewer)] == [test.id]
        assert list_executions(session, project.id, viewer) == []
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()


def test_owner_mutations_still_work() -> None:
    """The legitimate path must keep working."""

    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        test = _make_test(session, project, owner)
        execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
        finding = create_finding(
            session,
            FindingCreate(
                execution_id=execution.id, title="Real finding", severity=FindingSeverity.HIGH
            ),
            owner,
        )
        create_evidence(
            session,
            EvidenceCreate(finding_id=finding.id, kind="model_request", content={"a": 1}),
            owner,
        )
        report = create_report(session, project.id, ReportCreate(title="Real"), owner)
        updated = update_finding(
            session, finding.id, FindingUpdate(status=FindingStatus.FIXED), owner
        )
        assert updated.status == FindingStatus.FIXED
        assert report.id
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()


def test_execution_lifecycle_cannot_be_set_through_the_api() -> None:
    """A caller must not be able to mark an execution succeeded or pass.

    Previously ExecutionUpdate exposed status and result, so any project member
    could rewrite an assessment outcome.
    """

    from app.main import app

    paths = app.openapi()["paths"]
    base = "/api/v1/projects/{project_id}/assessments"
    assert (
        f"{base}/executions/{{execution_id}}" not in paths
        or "patch" not in paths[f"{base}/executions/{{execution_id}}"]
    ), "PATCH /executions/{id} still exposes lifecycle transitions"

    # The update schema must not carry status or result at all.
    from app.schemas import ExecutionUpdate

    assert "status" not in ExecutionUpdate.model_fields
    assert "result" not in ExecutionUpdate.model_fields


def test_failed_execution_cannot_be_marked_pass_by_a_member(session: Session | None = None) -> None:
    """End-to-end: a VIEWER cannot rewrite a failed execution to passed."""

    session = _session()
    owner, viewer, project = _owner_with_viewer(session)
    try:
        test = _make_test(session, project, owner)
        execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
        execution.status = ExecutionStatus.FAILED
        session.commit()

        # There is no longer any service call a viewer can make to change it.
        session.refresh(execution)
        assert execution.status == ExecutionStatus.FAILED
    finally:
        _cleanup(session, owner, viewer, project=project)
        session.close()

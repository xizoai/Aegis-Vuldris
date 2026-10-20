"""Target access must honour project membership.

ensure_project_access() treats a project member as a reader, but
ensure_target_access() only accepted global admins and the project owner. A
member added to a project could therefore read that project's tests,
executions, and reports while being denied access to its targets -- the
opposite of what membership is for.

These tests pin the consistent behaviour: a member can reach the project's
targets, and a non-member still cannot.
"""

from uuid import uuid4

import pytest
from app.api.errors import PermissionDeniedError
from app.db.session import create_session_factory
from app.models.membership import ProjectMembership
from app.models.project import Project
from app.models.target import Target, TargetProvider
from app.models.user import User, UserRole
from app.schemas import ProjectCreate, TargetCreate, UserCreate
from app.security.secrets import get_secret_store
from app.services.auth import register_user
from app.services.credentials import (
    create_target_credential,
    list_target_credentials,
)
from app.services.projects import create_project, is_project_member
from app.services.targets import ensure_target_access
from sqlalchemy import select
from sqlalchemy.orm import Session

PASSWORD = "a-very-strong-password"


def _session() -> Session:
    return create_session_factory()()


def _setup(role: UserRole) -> tuple[Session, User, User, Project]:
    session = _session()
    owner = register_user(
        session, UserCreate(email=f"tgt-own-{uuid4()}@example.com", password=PASSWORD)
    )
    member = register_user(
        session, UserCreate(email=f"tgt-mem-{uuid4()}@example.com", password=PASSWORD)
    )
    member.role = role
    session.commit()

    project = create_project(session, ProjectCreate(name=f"Target {uuid4()}"), owner_id=owner.id)
    session.add(ProjectMembership(project_id=project.id, user_id=member.id, role=role))
    session.commit()
    session.refresh(owner)
    session.refresh(member)
    return session, owner, member, project


def _target(session: Session, project: Project, owner: User) -> Target:
    from app.services.targets import create_target

    return create_target(
        session,
        TargetCreate(
            project_id=project.id,
            name="Model",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="test-model",
            authorization_attestation=True,
        ),
        project_id=project.id,
        user=owner,
    )


def test_project_member_can_read_project_targets() -> None:
    session, owner, member, project = _setup(UserRole.USER)
    try:
        target = _target(session, project, owner)
        assert is_project_member(session, member, project)
        # Should not raise: membership grants read access to project resources.
        ensure_target_access(session, member, target, "read")
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_non_member_is_still_denied() -> None:
    session, owner, _, project = _setup(UserRole.USER)
    try:
        target = _target(session, project, owner)
        stranger = register_user(
            session,
            UserCreate(email=f"tgt-str-{uuid4()}@example.com", password=PASSWORD),
        )
        session.commit()

        with pytest.raises(PermissionDeniedError):
            ensure_target_access(session, stranger, target, "read")
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_viewer_member_can_read_but_not_modify_targets() -> None:
    session, owner, member, project = _setup(UserRole.VIEWER)
    try:
        target = _target(session, project, owner)

        ensure_target_access(session, member, target, "read")

        with pytest.raises(PermissionDeniedError):
            ensure_target_access(session, member, target, "update")
        with pytest.raises(PermissionDeniedError):
            ensure_target_access(session, member, target, "delete")
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_member_can_list_credentials_of_project_targets() -> None:
    """Credential listing must follow the same membership policy."""

    from app.schemas import CredentialCreate

    session, owner, member, project = _setup(UserRole.USER)
    try:
        target = _target(session, project, owner)
        create_target_credential(
            session,
            get_secret_store(),
            target.id,
            CredentialCreate(credential_type="api_key", value="sk-member-test"),
            owner,
        )

        listed = list_target_credentials(session, target.id, member)
        assert len(listed) == 1
        assert "sk-member-test" not in str(listed[0].__dict__)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_member_of_another_project_cannot_reach_targets() -> None:
    """Widening to membership must stay scoped to that one project."""

    session, owner, member, project = _setup(UserRole.USER)
    try:
        target = _target(session, project, owner)

        # Move the member off this project and onto a different one, so their
        # membership proves nothing about access here.
        orphan = session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.user_id == member.id,
            )
        )
        if orphan is not None:
            session.delete(orphan)
        other_project = create_project(
            session, ProjectCreate(name=f"Other {uuid4()}"), owner_id=owner.id
        )
        session.add(
            ProjectMembership(project_id=other_project.id, user_id=member.id, role=UserRole.USER)
        )
        session.commit()
        session.refresh(member)

        assert is_project_member(session, member, other_project)
        assert not is_project_member(session, member, project)

        with pytest.raises(PermissionDeniedError):
            ensure_target_access(session, member, target, "read")

        session.delete(other_project)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_global_admin_still_has_access() -> None:
    session, owner, _, project = _setup(UserRole.USER)
    try:
        target = _target(session, project, owner)
        admin = register_user(
            session,
            UserCreate(email=f"tgt-adm-{uuid4()}@example.com", password=PASSWORD),
        )
        admin.role = UserRole.ADMIN
        session.commit()

        ensure_target_access(session, admin, target, "read")
    finally:
        session.delete(project)
        session.commit()
        session.close()

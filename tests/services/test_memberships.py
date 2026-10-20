"""Project membership service tests for Aegis Vuldris."""

from uuid import uuid4

import pytest
from app.api.errors import MembershipConflictError, PermissionDeniedError, ProjectNotFoundError
from app.db.session import create_session_factory
from app.models.membership import ProjectMembership
from app.models.project import Project
from app.models.user import User, UserRole
from app.schemas import (
    ProjectCreate,
    ProjectMembershipCreate,
    ProjectMembershipUpdate,
    UserCreate,
)
from app.services.auth import register_user
from app.services.memberships import (
    create_project_membership,
    delete_project_membership,
    list_project_memberships,
    update_project_membership,
)
from app.services.projects import create_project
from sqlalchemy.orm import Session


def _create_session() -> Session:
    return create_session_factory()()


def _register_user(
    session: Session,
    role: UserRole = UserRole.USER,
    email_suffix: str = "membership",
) -> User:
    """Register a user and optionally set a non-default platform role."""

    user = register_user(
        session,
        UserCreate(
            email=f"{email_suffix}-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )

    if role != UserRole.USER:
        user.role = role
        session.commit()
        session.refresh(user)

    return user


def _create_project(session: Session, owner: User | None) -> Project:
    """Create a project, optionally without a dedicated owner."""

    return create_project(
        session,
        ProjectCreate(name=f"Membership Project {uuid4()}"),
        owner_id=owner.id if owner is not None else None,
    )


def test_owner_can_add_and_list_members() -> None:
    session = _create_session()
    owner = _register_user(session)
    member = _register_user(session)
    project = _create_project(session, owner)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.VIEWER),
            owner,
        )
        assert membership.role == UserRole.VIEWER

        memberships = list_project_memberships(session, project.id, owner)
        assert any(m.user_id == member.id for m in memberships)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_non_owner_cannot_add_members() -> None:
    session = _create_session()
    owner = _register_user(session)
    stranger = _register_user(session)
    project = _create_project(session, owner)

    try:
        with pytest.raises(PermissionDeniedError):
            create_project_membership(
                session,
                project.id,
                ProjectMembershipCreate(user_id=stranger.id, role=UserRole.VIEWER),
                stranger,
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_member_can_view_project_members() -> None:
    session = _create_session()
    owner = _register_user(session)
    member = _register_user(session)
    project = _create_project(session, owner)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.VIEWER),
            owner,
        )
        memberships = list_project_memberships(session, project.id, member)
        assert membership.id in {m.id for m in memberships}
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_owner_can_update_and_delete_membership() -> None:
    session = _create_session()
    owner = _register_user(session)
    member = _register_user(session)
    project = _create_project(session, owner)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.VIEWER),
            owner,
        )
        updated = update_project_membership(
            session,
            membership.id,
            ProjectMembershipUpdate(role=UserRole.ADMIN),
            owner,
        )
        assert updated.role == UserRole.ADMIN

        assert delete_project_membership(session, membership.id, owner) is True
        assert session.get(ProjectMembership, membership.id) is None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_duplicate_membership_raises() -> None:
    session = _create_session()
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
        with pytest.raises(ProjectNotFoundError):
            create_project_membership(
                session,
                project.id,
                ProjectMembershipCreate(user_id=member.id, role=UserRole.VIEWER),
                owner,
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


# --- RBAC admin-count guardrails ---


def test_demote_last_admin_no_owner_raises() -> None:
    """Demoting the only admin on a project without an owner is blocked."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.ADMIN, email_suffix="demote-last")
    member = _register_user(session, email_suffix="demote-last-m")
    project = _create_project(session, owner=None)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.ADMIN),
            admin,
        )

        with pytest.raises(MembershipConflictError):
            update_project_membership(
                session,
                membership.id,
                ProjectMembershipUpdate(role=UserRole.USER),
                admin,
            )

        # Membership role should be unchanged.
        session.refresh(membership)
        assert membership.role == UserRole.ADMIN

        session.delete(membership)
        session.commit()
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_owner_can_demote_membership_admin() -> None:
    """A project owner can demote a membership admin because the owner remains an admin."""

    session = _create_session()
    owner = _register_user(session, email_suffix="owner-demote")
    member = _register_user(session, email_suffix="member-demote")
    project = _create_project(session, owner)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.ADMIN),
            owner,
        )

        updated = update_project_membership(
            session,
            membership.id,
            ProjectMembershipUpdate(role=UserRole.USER),
            owner,
        )

        assert updated.role == UserRole.USER
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_demote_admin_with_another_admin_succeeds() -> None:
    """Demoting one of several admins is allowed when another admin remains."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.ADMIN, email_suffix="demote-multi")
    member_a = _register_user(session, email_suffix="demote-multi-a")
    member_b = _register_user(session, email_suffix="demote-multi-b")
    project = _create_project(session, owner=None)

    try:
        membership_a = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member_a.id, role=UserRole.ADMIN),
            admin,
        )
        create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member_b.id, role=UserRole.ADMIN),
            admin,
        )

        updated = update_project_membership(
            session,
            membership_a.id,
            ProjectMembershipUpdate(role=UserRole.VIEWER),
            admin,
        )

        assert updated.role == UserRole.VIEWER
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_self_demotion_without_other_admin_raises() -> None:
    """A user cannot demote their own admin role when no other admin exists."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.SUPER_ADMIN, email_suffix="self-demote")
    project = _create_project(session, owner=None)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=admin.id, role=UserRole.ADMIN),
            admin,
        )

        with pytest.raises(MembershipConflictError):
            update_project_membership(
                session,
                membership.id,
                ProjectMembershipUpdate(role=UserRole.USER),
                admin,
            )

        session.refresh(membership)
        assert membership.role == UserRole.ADMIN

        session.delete(membership)
        session.commit()
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_self_demotion_with_other_admin_succeeds() -> None:
    """A user can demote their own admin role when another admin exists."""

    session = _create_session()
    admin_a = _register_user(session, role=UserRole.SUPER_ADMIN, email_suffix="self-demote-ok-a")
    member_b = _register_user(session, email_suffix="self-demote-ok-b")
    project = _create_project(session, owner=None)

    try:
        membership_a = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=admin_a.id, role=UserRole.ADMIN),
            admin_a,
        )
        create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member_b.id, role=UserRole.ADMIN),
            admin_a,
        )

        updated = update_project_membership(
            session,
            membership_a.id,
            ProjectMembershipUpdate(role=UserRole.USER),
            admin_a,
        )

        assert updated.role == UserRole.USER
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_demote_non_admin_role_has_no_guard() -> None:
    """Demoting a non-admin membership role is never blocked."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.ADMIN, email_suffix="no-guard")
    member = _register_user(session, email_suffix="no-guard-m")
    project = _create_project(session, owner=None)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.USER),
            admin,
        )

        updated = update_project_membership(
            session,
            membership.id,
            ProjectMembershipUpdate(role=UserRole.VIEWER),
            admin,
        )

        assert updated.role == UserRole.VIEWER
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_delete_last_admin_no_owner_raises() -> None:
    """Removing the only admin on a project without an owner is blocked."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.ADMIN, email_suffix="del-last")
    member = _register_user(session, email_suffix="del-last-m")
    project = _create_project(session, owner=None)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.ADMIN),
            admin,
        )

        with pytest.raises(MembershipConflictError):
            delete_project_membership(session, membership.id, admin)

        # Membership should still exist.
        assert session.get(ProjectMembership, membership.id) is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_delete_admin_with_another_admin_succeeds() -> None:
    """Removing one of several admins is allowed when another admin remains."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.ADMIN, email_suffix="del-multi")
    member_a = _register_user(session, email_suffix="del-multi-a")
    member_b = _register_user(session, email_suffix="del-multi-b")
    project = _create_project(session, owner=None)

    try:
        membership_a = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member_a.id, role=UserRole.ADMIN),
            admin,
        )
        create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member_b.id, role=UserRole.ADMIN),
            admin,
        )

        assert delete_project_membership(session, membership_a.id, admin) is True
        assert session.get(ProjectMembership, membership_a.id) is None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_self_removal_without_other_admin_raises() -> None:
    """A user cannot delete their own admin membership when no other admin exists."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.SUPER_ADMIN, email_suffix="self-del")
    project = _create_project(session, owner=None)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=admin.id, role=UserRole.ADMIN),
            admin,
        )

        with pytest.raises(MembershipConflictError):
            delete_project_membership(session, membership.id, admin)

        assert session.get(ProjectMembership, membership.id) is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_delete_non_admin_succeeds() -> None:
    """Removing a non-admin membership is never blocked by the admin guardrail."""

    session = _create_session()
    admin = _register_user(session, role=UserRole.ADMIN, email_suffix="del-user")
    member = _register_user(session, email_suffix="del-user-m")
    project = _create_project(session, owner=None)

    try:
        membership = create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=member.id, role=UserRole.VIEWER),
            admin,
        )

        assert delete_project_membership(session, membership.id, admin) is True
        assert session.get(ProjectMembership, membership.id) is None
    finally:
        session.delete(project)
        session.commit()
        session.close()

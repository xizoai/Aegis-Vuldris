"""Project membership service operations for Aegis Vuldris."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import MembershipConflictError, ProjectNotFoundError
from app.models.membership import ProjectMembership
from app.models.project import Project
from app.models.user import User, UserRole
from app.schemas import ProjectMembershipCreate, ProjectMembershipUpdate
from app.services.audit import record_audit_event
from app.services.projects import ensure_project_access

MEMBERSHIP_ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.USER}

_MEMBERSHIP_ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}


def _is_admin_role(role: UserRole) -> bool:
    """Return True if a project-level role grants administrative privileges."""

    return role in _MEMBERSHIP_ADMIN_ROLES


def _project_admin_count(
    session: Session,
    project_id: UUID,
    exclude_membership_id: UUID | None = None,
) -> int:
    """Count how many administrators a project has.

    A project administrator is either the project owner (``project.owner_id``)
    or a membership whose role is ADMIN or SUPER_ADMIN. When
    ``exclude_membership_id`` is provided, that membership is not counted
    (used to evaluate the post-operation state before a demotion or deletion).
    """

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()

    query = select(ProjectMembership).where(
        ProjectMembership.project_id == project_id,
        ProjectMembership.role.in_(_MEMBERSHIP_ADMIN_ROLES),
    )
    if exclude_membership_id is not None:
        query = query.where(ProjectMembership.id != exclude_membership_id)

    admin_memberships = session.scalars(query).all()

    # The project owner is always an administrator regardless of membership.
    owner_count = 1 if project.owner_id is not None else 0
    member_count = len(admin_memberships)

    # A user can be both the owner and a membership admin; don't double count.
    if any(m.user_id == project.owner_id for m in admin_memberships):
        member_count -= 1

    return owner_count + member_count


def _ensure_admin_remains(
    session: Session,
    project_id: UUID,
    acting_user_id: UUID,
    member_user_id: UUID,
    exclude_membership_id: UUID | None = None,
) -> None:
    """Guard that a project will still have at least one administrator.

    Called before demoting or removing a membership that currently holds an
    admin role. If the acting user *is* the member being modified (self-
    demotion / self-removal), an additional admin must be present so the
    user does not lock themselves out.
    """

    if _project_admin_count(session, project_id, exclude_membership_id=exclude_membership_id) > 0:
        return

    if member_user_id == acting_user_id:
        raise MembershipConflictError(
            "Cannot remove your own administrator access — at least one other "
            "project administrator must exist first."
        )
    raise MembershipConflictError(
        "Cannot demote the last project administrator. Assign another "
        "administrator before making this change."
    )


def get_membership(
    session: Session,
    membership_id: UUID,
) -> ProjectMembership:
    """Return a membership by ID or raise ProjectNotFoundError."""

    membership = session.get(ProjectMembership, membership_id)
    if membership is None:
        raise ProjectNotFoundError()
    return membership


def list_project_memberships(
    session: Session,
    project_id: UUID,
    user: User,
) -> list[ProjectMembership]:
    """Return memberships for a project the user may read."""

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "read")

    return list(
        session.scalars(
            select(ProjectMembership)
            .where(ProjectMembership.project_id == project_id)
            .order_by(ProjectMembership.created_at, ProjectMembership.id)
        ).all()
    )


def create_project_membership(
    session: Session,
    project_id: UUID,
    payload: ProjectMembershipCreate,
    user: User,
) -> ProjectMembership:
    """Add a user to an authorized project."""

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "update")

    member = session.scalar(select(User).where(User.id == payload.user_id))
    if member is None:
        raise ProjectNotFoundError()

    existing = session.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == payload.user_id,
        )
    )
    if existing is not None:
        raise ProjectNotFoundError()

    membership = ProjectMembership(
        project_id=project_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    session.add(membership)
    session.commit()
    session.refresh(membership)

    record_audit_event(
        session,
        actor_id=user.id,
        action="project_membership.created",
        resource_type="project_membership",
        resource_id=str(membership.id),
        event_metadata={
            "project_id": str(project_id),
            "user_id": str(payload.user_id),
            "role": payload.role.value,
        },
    )

    return membership


def update_project_membership(
    session: Session,
    membership_id: UUID,
    payload: ProjectMembershipUpdate,
    user: User,
) -> ProjectMembership:
    """Update the role of a membership within an authorized project."""

    membership = get_membership(session, membership_id)
    project = session.get(Project, membership.project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "update")

    target = session.scalar(select(User).where(User.id == membership.user_id))
    if target is None:
        raise ProjectNotFoundError()

    # Guard against demoting the last remaining project administrator.
    if _is_admin_role(membership.role) and not _is_admin_role(payload.role):
        _ensure_admin_remains(
            session,
            project.id,
            user.id,
            membership.user_id,
            exclude_membership_id=membership_id,
        )

    membership.role = payload.role
    session.commit()
    session.refresh(membership)

    record_audit_event(
        session,
        actor_id=user.id,
        action="project_membership.updated",
        resource_type="project_membership",
        resource_id=str(membership.id),
        event_metadata={"role": payload.role.value},
    )

    return membership


def delete_project_membership(
    session: Session,
    membership_id: UUID,
    user: User,
) -> bool:
    """Remove a membership from an authorized project."""

    membership = get_membership(session, membership_id)
    project = session.get(Project, membership.project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "update")

    # Guard against removing the last remaining project administrator.
    if _is_admin_role(membership.role):
        _ensure_admin_remains(
            session,
            project.id,
            user.id,
            membership.user_id,
            exclude_membership_id=membership_id,
        )

    session.delete(membership)
    session.commit()

    record_audit_event(
        session,
        actor_id=user.id,
        action="project_membership.deleted",
        resource_type="project_membership",
        resource_id=str(membership_id),
        event_metadata={"project_id": str(membership.project_id)},
    )

    return True


def can_read_project_with_membership(
    session: Session,
    user: User,
    project: Project,
) -> bool:
    """Return whether a user may read a project via direct membership."""

    if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} or project.owner_id == user.id:
        return True
    membership = session.scalar(
        select(ProjectMembership)
        .where(
            ProjectMembership.project_id == project.id,
            ProjectMembership.user_id == user.id,
        )
        .limit(1)
    )
    return membership is not None

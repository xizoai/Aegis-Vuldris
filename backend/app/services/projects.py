"""Project service operations for Aegis Vuldris."""

from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.api.errors import PermissionDeniedError, ProjectNotFoundError, TargetNotFoundError
from app.models.membership import ProjectMembership
from app.models.project import Project
from app.models.target import Target
from app.models.user import User, UserRole
from app.schemas import ProjectCreate, ProjectUpdate
from app.services.audit import record_audit_event

ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}


def can_read_project(user: User, project: Project) -> bool:
    """Return whether a user may read a project at a role level.

    Note: this does not consider direct project membership, which requires a
    database session. Use ``can_read_project_with_membership`` when membership
    access must be evaluated.
    """

    return user.role in ADMIN_ROLES or project.owner_id == user.id


def is_project_member(session: Session, user: User, project: Project) -> bool:
    """Return whether a user has a direct membership in a project."""

    if can_read_project(user, project):
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


def can_mutate_project(user: User, project: Project) -> bool:
    """Return whether a user may mutate a project."""

    return user.role != UserRole.VIEWER and can_read_project(user, project)


# Operations that change state and therefore require mutation rights, not
# merely read access. Named explicitly so a call site cannot silently pass a
# verb that happens not to be in this set: a mutation that used "read" would be
# allowed for a VIEWER.
MUTATING_OPERATIONS = frozenset(
    {
        "create",
        "update",
        "delete",
        "run",
        "cancel",
        "seed",
        "generate",
    }
)


def ensure_project_access(
    session: Session,
    user: User,
    project: Project,
    operation: str,
) -> None:
    """Authorize a project operation and record denied attempts."""

    is_reader = can_read_project(user, project) or is_project_member(session, user, project)

    if not is_reader:
        record_audit_event(
            session,
            actor_id=user.id,
            action="project.access_denied",
            resource_type="project",
            resource_id=str(project.id),
            event_metadata={"operation": operation},
        )
        raise PermissionDeniedError()

    if operation in MUTATING_OPERATIONS and not can_mutate_project(user, project):
        record_audit_event(
            session,
            actor_id=user.id,
            action="project.access_denied",
            resource_type="project",
            resource_id=str(project.id),
            event_metadata={"operation": operation},
        )
        raise PermissionDeniedError()


def create_project(
    session: Session,
    payload: ProjectCreate,
    owner_id: UUID | None,
) -> Project:
    """Create and persist a new project owned by the authenticated user."""

    project = Project(
        owner_id=owner_id,
        name=payload.name,
        description=payload.description,
    )

    session.add(project)
    session.commit()
    session.refresh(project)

    return project


def get_project(
    session: Session,
    project_id: UUID,
) -> Project | None:
    """Return a project by ID, or None when it does not exist."""

    return session.get(Project, project_id)


def get_project_for_user(
    session: Session,
    project_id: UUID,
    user: User,
    *,
    allow_mutation: bool = False,
) -> Project:
    """Return an authorized project or raise a standardized error."""

    project = get_project(session, project_id)

    if project is None:
        raise ProjectNotFoundError()

    ensure_project_access(session, user, project, "read" if not allow_mutation else "update")

    if allow_mutation and not can_mutate_project(user, project):
        raise PermissionDeniedError()

    return project


def list_projects_for_user(
    session: Session,
    user: User,
) -> list[Project]:
    """Return projects visible to a user, filtered by ownership unless administrative."""

    statement = select(Project)

    if user.role not in ADMIN_ROLES:
        statement = statement.where(
            or_(
                Project.owner_id == user.id,
                exists()
                .where(
                    ProjectMembership.project_id == Project.id,
                    ProjectMembership.user_id == user.id,
                )
                .correlate(Project),
            )
        )

    statement = statement.order_by(Project.created_at, Project.id)
    return list(session.scalars(statement).all())


def update_project(
    session: Session,
    project_id: UUID,
    payload: ProjectUpdate,
    user: User,
) -> Project | None:
    """Update an existing project and return it, or None if absent."""

    project = get_project(session, project_id)

    if project is None:
        return None

    ensure_project_access(session, user, project, "update")

    changes = payload.model_dump(exclude_unset=True)

    # A judge target must belong to this project. A target of another project
    # is treated as absent rather than reported as existing, so the error
    # cannot be used to probe for other projects' targets.
    if changes.get("judge_target_id") is not None:
        judge_target = session.get(Target, changes["judge_target_id"])
        if judge_target is None or judge_target.project_id != project.id:
            raise TargetNotFoundError()

    for field, value in changes.items():
        setattr(project, field, value)

    session.commit()
    session.refresh(project)

    return project


def delete_project(
    session: Session,
    project_id: UUID,
    user: User,
) -> bool:
    """Delete an authorized project and return whether it existed."""

    project = get_project(session, project_id)

    if project is None:
        return False

    ensure_project_access(session, user, project, "delete")

    session.delete(project)
    session.commit()

    return True

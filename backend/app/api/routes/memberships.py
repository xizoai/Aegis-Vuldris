"""Project membership API routes for Aegis Vuldris."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import (
    ProjectMembershipCreate,
    ProjectMembershipResponse,
    ProjectMembershipUpdate,
)
from app.security.dependencies import CurrentUser
from app.services.audit import record_audit_event
from app.services.memberships import (
    create_project_membership,
    delete_project_membership,
    get_membership,
    list_project_memberships,
    update_project_membership,
)

router = APIRouter(
    prefix="/projects/{project_id}/members",
    tags=["project-memberships"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "",
    response_model=ProjectMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_membership_endpoint(
    project_id: UUID,
    payload: ProjectMembershipCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ProjectMembershipResponse:
    """Add a user to an authorized project."""

    membership = create_project_membership(session, project_id, payload, current_user)
    return ProjectMembershipResponse.model_validate(membership)


@router.get(
    "",
    response_model=list[ProjectMembershipResponse],
)
async def list_memberships_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[ProjectMembershipResponse]:
    """Return memberships for an authorized project."""

    memberships = list_project_memberships(session, project_id, current_user)
    return [ProjectMembershipResponse.model_validate(m) for m in memberships]


@router.patch(
    "/{membership_id}",
    response_model=ProjectMembershipResponse,
)
async def update_membership_endpoint(
    project_id: UUID,
    membership_id: UUID,
    payload: ProjectMembershipUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ProjectMembershipResponse:
    """Update the role of a membership in an authorized project."""

    membership = update_project_membership(session, membership_id, payload, current_user)
    if membership.project_id != project_id:
        from app.api.errors import ProjectNotFoundError

        raise ProjectNotFoundError()
    return ProjectMembershipResponse.model_validate(membership)


@router.delete(
    "/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_membership_endpoint(
    project_id: UUID,
    membership_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> None:
    """Remove a membership from an authorized project."""

    existing = get_membership(session, membership_id)
    if existing.project_id != project_id:
        from app.api.errors import ProjectNotFoundError

        raise ProjectNotFoundError()
    if not delete_project_membership(session, membership_id, current_user):
        from app.api.errors import ProjectNotFoundError

        raise ProjectNotFoundError()

    record_audit_event(
        session,
        actor_id=current_user.id,
        action="project_membership.deleted",
        resource_type="project_membership",
        resource_id=str(membership_id),
    )

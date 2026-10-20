"""Project API routes for Aegis Vuldris."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.errors import ProjectNotFoundError
from app.db.session import get_db_session
from app.schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from app.security.dependencies import CurrentUser
from app.services.audit import record_audit_event
from app.services.projects import (
    create_project,
    delete_project,
    get_project_for_user,
    list_projects_for_user,
    update_project,
)

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_endpoint(
    payload: ProjectCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ProjectResponse:
    """Create a project owned by the authenticated user."""

    project = create_project(session, payload, owner_id=current_user.id)

    record_audit_event(
        session,
        actor_id=current_user.id,
        action="project.created",
        resource_type="project",
        resource_id=str(project.id),
        event_metadata={"owner_id": str(current_user.id)},
    )

    return ProjectResponse.model_validate(project)


@router.get(
    "",
    response_model=list[ProjectResponse],
)
async def list_projects_endpoint(
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[ProjectResponse]:
    """Return projects visible to the authenticated user."""

    projects = list_projects_for_user(session, current_user)

    return [ProjectResponse.model_validate(project) for project in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def get_project_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ProjectResponse:
    """Return an authorized project by ID."""

    project = get_project_for_user(session, project_id, current_user)

    return ProjectResponse.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def update_project_endpoint(
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ProjectResponse:
    """Update an authorized existing project."""

    project = update_project(
        session,
        project_id,
        payload,
        current_user,
    )

    if project is None:
        raise ProjectNotFoundError()

    record_audit_event(
        session,
        actor_id=current_user.id,
        action="project.updated",
        resource_type="project",
        resource_id=str(project.id),
        event_metadata={
            "changed_fields": sorted(payload.model_dump(exclude_unset=True)),
        },
    )

    return ProjectResponse.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> None:
    """Delete an authorized existing project."""

    deleted = delete_project(
        session,
        project_id,
        current_user,
    )

    if not deleted:
        raise ProjectNotFoundError()

    record_audit_event(
        session,
        actor_id=current_user.id,
        action="project.deleted",
        resource_type="project",
        resource_id=str(project_id),
    )

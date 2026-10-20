"""Project membership API schemas for Aegis Vuldris."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class ProjectMembershipCreate(BaseModel):
    """Request schema for adding a user to a project."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UUID
    role: UserRole = UserRole.USER


class ProjectMembershipUpdate(BaseModel):
    """Request schema for updating a membership role."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: UserRole


class ProjectMembershipResponse(BaseModel):
    """Response schema for a project membership."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    role: UserRole
    created_at: datetime
    updated_at: datetime

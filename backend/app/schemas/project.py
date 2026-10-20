"""Project API schemas for Aegis Vuldris."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Request schema for creating a project."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectUpdate(BaseModel):
    """Request schema for updating a project."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    # The target whose model grades this project's judge-model tests. Must be
    # a target belonging to this project; send null to clear it.
    judge_target_id: UUID | None = None


class ProjectResponse(BaseModel):
    """Response schema for a project."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )

    id: UUID
    owner_id: UUID | None
    name: str
    description: str | None
    judge_target_id: UUID | None
    created_at: datetime
    updated_at: datetime

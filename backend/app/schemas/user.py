"""User API schemas for Aegis Vuldris."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Request schema for registering a new user."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    """Response schema for a user.

    Never includes the password or hashed password.
    """

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )

    id: UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

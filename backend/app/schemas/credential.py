"""Target credential API schemas for Aegis Vuldris."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CredentialCreate(BaseModel):
    """Request schema for creating a target credential."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    credential_type: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=1_000_000)


class CredentialResponse(BaseModel):
    """Response schema for a target credential.

    The plaintext credential value is never included in this response.
    """

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )

    id: UUID
    target_id: UUID
    credential_type: str
    version: int
    revoked: bool
    created_at: datetime
    updated_at: datetime

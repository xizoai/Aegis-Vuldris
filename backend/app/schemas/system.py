"""System API schemas for Aegis Vuldris."""

from pydantic import BaseModel, ConfigDict


class SystemInfoResponse(BaseModel):
    """Response schema for Aegis Vuldris system information."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    environment: str
    status: str


class ReadinessResponse(BaseModel):
    """Response schema for a readiness check."""

    model_config = ConfigDict(extra="forbid")

    status: str
    database: str

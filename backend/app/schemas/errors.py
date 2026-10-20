"""Common API error schemas for Aegis Vuldris."""

from pydantic import BaseModel, Field


class APIError(BaseModel):
    """Machine-readable API error details."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class APIErrorResponse(BaseModel):
    """Standard API error response envelope."""

    error: APIError

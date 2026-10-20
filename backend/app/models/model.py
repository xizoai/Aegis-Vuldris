"""Normalized model interaction contracts for Aegis Vuldris adapters."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelMessage(BaseModel):
    """A normalized conversational message."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=1_000_000)

    @field_validator("content")
    @classmethod
    def reject_empty_content(cls, value: str) -> str:
        """Reject whitespace-only message content."""

        if not value.strip():
            raise ValueError("message content must not be empty")
        return value


class ModelRequest(BaseModel):
    """Provider-independent request sent to a model target."""

    model_config = ConfigDict(extra="forbid")

    messages: list[ModelMessage] = Field(min_length=1, max_length=100)
    # Optional per-request model override. Adapters prefer it over the
    # target's own model, which is how judge-model grading can pin the judge
    # to a specific model on the same endpoint without registering a second
    # target per model.
    model: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = Field(default=None, max_length=1_000_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    stop: list[str] | None = Field(default=None, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stop")
    @classmethod
    def normalize_stop(cls, value: list[str] | None) -> list[str] | None:
        """Normalize stop sequences without allowing empty values."""

        if value is None:
            return None
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("stop sequences must not be empty")
        return normalized


class ModelUsage(BaseModel):
    """Normalized provider usage metadata."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class ModelResponse(BaseModel):
    """Normalized result returned by a model target."""

    model_config = ConfigDict(extra="forbid")

    output: str
    finish_reason: str | None = None
    model: str | None = None
    usage: ModelUsage | None = None
    latency_seconds: float = Field(default=0.0, ge=0)
    provider_request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

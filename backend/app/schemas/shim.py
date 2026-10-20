"""OpenAI-compatible request/response schemas for the Aegis LLM shim.

Deliberately narrow. Tools vary in what they send; accepting everything would
make the shim silently broad, and fields Aegis does not forward (or that name
destinations, tools, or functions) get rejected rather than silently passed
through. ``model`` is accepted because every OpenAI client sends it, but is
descriminated at conversion time -- the target's model wins.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Bounds mirror the native execution path's ModelRequest so the shim can never
# push a larger payload through than a user-driven run would.
_MAX_MESSAGES = 100
_MAX_MESSAGE_CHARS = 100_000
_MAX_COMPLETION_TOKENS = 100_000
_MAX_STOP_SEQUENCES = 50


class ChatMessage(BaseModel):
    """One OpenAI-shaped chat message."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=_MAX_MESSAGE_CHARS)


class ChatCompletionRequest(BaseModel):
    """OpenAI `chat/completions` request, minus anything that names a route."""

    model_config = ConfigDict(extra="forbid")

    # Accepted for OpenAI-client compatibility, validated, then dropped:
    # forwarding it would let a tool address a different deployment on the
    # same endpoint than the one the authorizing scan bound.
    model: str | None = None
    messages: list[ChatMessage] = Field(min_length=1, max_length=_MAX_MESSAGES)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=_MAX_COMPLETION_TOKENS)
    stop: str | list[str] | None = None
    # Streamed responses cannot be rebuilt into the flat OpenAI shape, so they
    # are refused rather than silently non-streamed.
    stream: bool | None = None
    # OpenAI clients commonly send these; harmless, accepted, not forwarded
    # (only the bound target's configured deployment parameters apply).
    user: str | None = Field(default=None, max_length=200)
    top_p: float | None = Field(default=None, ge=0, le=1)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)

    @field_validator("stop")
    @classmethod
    def _normalize_stop(cls, value: str | list[str] | None) -> list[str] | None:
        """Accept a single string or a list; empty items are useless."""

        if value is None:
            return None
        items = [value] if isinstance(value, str) else value
        if len(items) > _MAX_STOP_SEQUENCES:
            raise ValueError("too many stop sequences")
        normalized = [item.strip() for item in items]
        if any(not item for item in normalized):
            raise ValueError("stop sequences must not be empty")
        return normalized

    @model_validator(mode="after")
    def refuse_streaming(self) -> "ChatCompletionRequest":
        """Streamed responses cannot be rebuilt into the flat OpenAI shape."""

        if self.stream:
            raise ValueError("streamed responses are not supported for external scans")
        return self


class ChatCompletionChoice(BaseModel):
    """One OpenAI-shaped completion choice."""

    model_config = ConfigDict(extra="forbid")

    index: int = 0
    message: dict[str, Any]
    finish_reason: str | None = None


class ChatCompletionUsage(BaseModel):
    """Token usage echoed back in the OpenAI shape."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ChatCompletionResponse(BaseModel):
    """OpenAI `chat.completion` shape."""

    model_config = ConfigDict(extra="forbid")

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice] = Field(min_length=1)
    usage: ChatCompletionUsage | None = None


__all__ = [
    "ChatCompletionChoice",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionUsage",
    "ChatMessage",
]

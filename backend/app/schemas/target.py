"""Target API schemas for Aegis Vuldris."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import get_settings
from app.models.target import TargetProvider, TargetStatus
from app.security.network import is_restricted_endpoint_literal

# Path segments that are request paths, never part of a base URL.
#
# The endpoint is a BASE URL: Aegis Vuldris appends the provider's own path, so a
# value that already contains one of these produces a doubled path and an
# opaque HTTP 404 at run time (for example
# https://openrouter.ai/api/v1/chat/completions/api/chat). This is the
# single most common configuration mistake, so it is rejected up front.
#
# All known request paths are rejected for every fixed-path provider, not just
# the selected one. A user who pasted a hosted OpenAI-compatible URL but chose
# "Ollama" is mismatched in both ways, and checking only the chosen provider's
# suffix would miss it.
#
# CUSTOM_REST is excluded because its path is configurable and defaults to
# none, so the full URL is legitimate there.
PROVIDER_REQUEST_PATHS: tuple[str, ...] = (
    "/chat/completions",
    "/api/chat",
)


def _validate_endpoint_is_base_url(endpoint: str, provider: TargetProvider) -> None:
    """Reject an endpoint that already contains a provider request path."""

    if provider == TargetProvider.CUSTOM_REST:
        return

    path = urlsplit(endpoint).path.rstrip("/").lower()
    for request_path in PROVIDER_REQUEST_PATHS:
        if path.endswith(request_path) or request_path in path:
            raise ValueError(
                "endpoint must be the base URL, not the full request path. "
                f"Aegis Vuldris appends the request path itself, so enter the URL up "
                f"to but not including '{request_path}' (for example "
                "https://api.example.com/v1)."
            )


class TargetCreate(BaseModel):
    """Request schema for creating a project target."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    provider: TargetProvider
    endpoint: str = Field(min_length=1, max_length=2048)
    model: str | None = Field(default=None, max_length=255)
    # Model profile: captured in every run manifest so a result identifies the
    # exact model revision and generation settings that produced it.
    model_version: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = Field(default=None, max_length=1_000_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    status: TargetStatus = TargetStatus.ACTIVE
    authorization_attestation: Literal[True] = Field(
        description=(
            "Confirms the caller is authorized to security-test this target "
            "(e.g. they own it, or have explicit permission from its owner). "
            "Aegis Vuldris is a security testing tool; running it against a system "
            "without authorization may be illegal. This must be explicitly "
            "set to true — Aegis Vuldris refuses to create a target otherwise."
        ),
    )

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        """Accept only ordinary HTTP or HTTPS target endpoints."""

        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("endpoint must be an absolute http or https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("endpoint must not contain credentials")
        if not get_settings().allow_local_targets and is_restricted_endpoint_literal(value):
            raise ValueError("loopback and private target addresses are not permitted")
        return value

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, value: list[str]) -> list[str]:
        """Normalize capability names without allowing empty entries."""

        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("capabilities must not contain empty values")
        return normalized

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> "TargetCreate":
        """Require a model identifier for model-backed providers."""

        if (
            self.provider in {TargetProvider.OPENAI_COMPATIBLE, TargetProvider.OLLAMA}
            and not self.model
        ):
            raise ValueError("model is required for openai_compatible and ollama targets")
        _validate_endpoint_is_base_url(self.endpoint, self.provider)
        return self


class TargetUpdate(BaseModel):
    """Request schema for updating a project target."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    provider: TargetProvider | None = None
    endpoint: str | None = Field(default=None, min_length=1, max_length=2048)
    model: str | None = Field(default=None, max_length=255)
    model_version: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = Field(default=None, max_length=1_000_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    capabilities: list[str] | None = Field(default=None, max_length=50)
    timeout_seconds: float | None = Field(default=None, gt=0, le=3600)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10000)
    status: TargetStatus | None = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        """Accept only ordinary HTTP or HTTPS target endpoints."""

        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("endpoint must be an absolute http or https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("endpoint must not contain credentials")
        if not get_settings().allow_local_targets and is_restricted_endpoint_literal(value):
            raise ValueError("loopback and private target addresses are not permitted")
        return value

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, value: list[str] | None) -> list[str] | None:
        """Normalize capability names without allowing empty entries."""

        if value is None:
            return None
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("capabilities must not contain empty values")
        return normalized

    @model_validator(mode="after")
    def require_update_field(self) -> "TargetUpdate":
        """Reject empty update payloads."""

        if not self.model_fields_set:
            raise ValueError("at least one target field must be supplied")
        return self

    @model_validator(mode="after")
    def validate_endpoint_against_provider(self) -> "TargetUpdate":
        """Apply the base-URL rule when the provider is known.

        A partial update may supply only the endpoint or only the provider, so
        the check runs when the endpoint is present and the provider is either
        supplied now or unchanged. Without the provider the pairing cannot be
        determined, so the value is left to the create path or a later update.
        """

        if self.endpoint is None:
            return self
        if self.provider is not None:
            _validate_endpoint_is_base_url(self.endpoint, self.provider)
        return self


class TargetResponse(BaseModel):
    """Response schema for a target."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )

    id: UUID
    project_id: UUID
    name: str
    description: str | None
    provider: TargetProvider
    endpoint: str
    model: str | None
    model_version: str | None
    system_prompt: str | None
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    seed: int | None
    capabilities: list[str]
    timeout_seconds: float
    rate_limit_per_minute: int
    status: TargetStatus
    authorization_attested_by: UUID | None
    authorization_attested_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelDiscoveryRequest(BaseModel):
    """Request schema for listing the models a provider endpoint offers."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: TargetProvider
    endpoint: str = Field(min_length=1, max_length=2048)
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Transient only: used as Bearer auth for this single provider request and
    # never persisted by this endpoint. Secrets are stored exclusively through
    # the target credential endpoint (encrypted at rest). ``repr=False`` keeps
    # the value out of accidental debug output.
    api_key: str | None = Field(default=None, max_length=4096, repr=False)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        """Accept only ordinary HTTP or HTTPS target endpoints."""

        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("endpoint must be an absolute http or https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("endpoint must not contain credentials")
        return value

    @model_validator(mode="after")
    def validate_endpoint_is_base_url(self) -> "ModelDiscoveryRequest":
        """Reject a full request path so discovery probes the same URL as runs."""

        _validate_endpoint_is_base_url(self.endpoint, self.provider)
        return self


class ModelDiscoveryResponse(BaseModel):
    """Response schema listing the models available at a provider endpoint."""

    model_config = ConfigDict(extra="forbid")

    provider: TargetProvider
    endpoint: str
    models: list[str]

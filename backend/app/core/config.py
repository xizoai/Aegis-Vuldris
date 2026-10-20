"""Centralized application configuration for Aegis Vuldris."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Aegis Vuldris", min_length=1)
    app_env: Literal["development", "testing", "staging", "production"] = "development"
    database_url: str = Field(default="")
    secret_key: str = Field(default="")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    jwt_algorithm: str = Field(default="HS256", min_length=1)
    access_token_expire_minutes: int = Field(default=30, gt=0)
    allow_local_targets: bool = Field(default=False)
    allow_third_party_plugins: bool = Field(default=True)

    # Shared secret the external scan runner presents on the internal claim and
    # report endpoints. Empty disables those endpoints entirely, so a deployment
    # that does not run external scans cannot expose them by accident.
    runner_service_token: str = Field(default="")
    # A runner claim older than this is treated as abandoned and requeued. The
    # runner is expected to keep a claim short in phase 0; phase 5 adds
    # heartbeats so long garak/PyRIT runs can extend their lease.
    runner_claim_lease_seconds: int = Field(default=3600, gt=0)

    # Lifetime of the scan-scoped LLM token minted at claim time. It is already
    # invalid as soon as the scan leaves "running", so this is only a backstop,
    # but it keeps a leaked token from living longer than a plausible scan.
    external_scan_token_expire_minutes: int = Field(default=240, gt=0)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Require a non-empty secret key outside development/testing."""

        if self.app_env in {"staging", "production"} and not self.secret_key.strip():
            raise ValueError(
                "SECRET_KEY must be configured for staging and production environments."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""

    return Settings()

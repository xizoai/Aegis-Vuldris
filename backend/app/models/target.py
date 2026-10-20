"""Target database model for Aegis Vuldris."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TargetProvider(StrEnum):
    """Supported target provider families."""

    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"
    CUSTOM_REST = "custom_rest"


class TargetStatus(StrEnum):
    """Lifecycle state for a registered target."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class Target(Base):
    """A project-scoped target configuration for model integration."""

    __tablename__ = "targets"
    __table_args__ = (
        CheckConstraint("timeout_seconds > 0", name="ck_targets_timeout_seconds_positive"),
        CheckConstraint(
            "rate_limit_per_minute > 0",
            name="ck_targets_rate_limit_per_minute_positive",
        ),
        CheckConstraint(
            "temperature IS NULL OR (temperature >= 0 AND temperature <= 2)",
            name="ck_targets_temperature_range",
        ),
        CheckConstraint(
            "top_p IS NULL OR (top_p >= 0 AND top_p <= 1)",
            name="ck_targets_top_p_range",
        ),
        CheckConstraint(
            "max_tokens IS NULL OR max_tokens > 0",
            name="ck_targets_max_tokens_positive",
        ),
        CheckConstraint(
            "seed IS NULL OR seed >= 0",
            name="ck_targets_seed_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provider: Mapped[TargetProvider] = mapped_column(
        SAEnum(
            TargetProvider,
            name="target_provider",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )

    endpoint: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    model: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # The model identifier alone is not a reproducible model version: providers
    # update the weights behind the same name. This is the operator-declared
    # version/revision (for example a dated snapshot or a local digest) and is
    # captured in every run manifest.
    model_version: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Optional target-level system prompt. A test case's own system prompt
    # overrides it; otherwise every request for this target carries it.
    system_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Generation defaults. A test case's explicit value overrides the target
    # default; otherwise these are what the target is actually run with.
    temperature: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    top_p: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    seed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    capabilities: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    timeout_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("30.0"),
    )

    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("60"),
    )

    status: Mapped[TargetStatus] = mapped_column(
        SAEnum(
            TargetStatus,
            name="target_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TargetStatus.ACTIVE,
        server_default=TargetStatus.ACTIVE.value,
        index=True,
    )

    authorization_attested_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    authorization_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

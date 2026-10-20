"""Evidence model for Aegis Vuldris."""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Sensitivity(enum.IntEnum):
    """How sensitive a piece of evidence is, mirroring service-level ordering."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


class Evidence(Base):
    """Evidence captured for a security finding."""

    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Classification of what this evidence contains, derived at write time from
    # the sensitive values detected in it. Lets restricted evidence be surfaced
    # differently without re-scanning stored content.
    #
    # Stored as an integer rather than a native enum: the Python side is an
    # IntEnum, and a check constraint states the same rule without the
    # enum/value mismatch that IntEnum has with SQLAlchemy's Enum type.
    sensitivity: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint(
            "sensitivity >= 0 AND sensitivity <= 3",
            name="ck_evidence_sensitivity_range",
        ),
        nullable=False,
        default=int(Sensitivity.INTERNAL),
        server_default=str(int(Sensitivity.INTERNAL)),
        index=True,
    )

    # Which sensitive kinds were found, e.g. ["api_key", "email"]. Recorded so a
    # reviewer can tell why evidence was classified as it was, and so a future
    # retention or access policy can key off the kind rather than re-scanning.
    detected_kinds: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    # Set when the persisted content was redacted before storage.
    redacted: Mapped[bool] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
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

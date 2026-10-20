"""Finding model for Aegis Vuldris."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FindingSeverity(StrEnum):
    """Severity classification for a security finding."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    """Lifecycle state for a security finding.

    ``FIXED`` is a human claim: someone applied a change. ``VERIFIED`` is
    deterministic evidence: the exact attack was re-run and no longer
    reproduces. Only the verification loop may set ``VERIFIED``; the API
    rejects it as an editable status.
    """

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    VERIFIED = "verified"
    WONT_FIX = "wont_fix"


class FindingConfirmation(StrEnum):
    """Whether a finding's observed result is trustworthy.

    The deterministic grader is lexical: a pattern match is a reproducible
    observation, not proof that the target was actually compromised. A
    response that echoes the attack's own wording, or a substring rule that
    happens to match a refusal, produces a candidate — plausible, but not
    established.

    A finding starts as ``CANDIDATE``. It becomes ``CONFIRMED`` only when a
    configured judge model or a human reviewer verifies that the attack
    actually landed; it becomes ``DISMISSED`` when one of them determines the
    response did not violate policy. Only confirmed findings make an
    execution ``fail``; confirmed and candidate findings are always visible
    so nothing is hidden.
    """

    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class Finding(Base):
    """A security finding produced by an execution."""

    __tablename__ = "findings"
    __table_args__ = (
        # A finding comes from exactly one origin. Native executions and
        # external scans are the only two, so a row naming both (or neither)
        # is a bug rather than a third kind of finding, and the database says
        # so instead of leaving the API to guess.
        CheckConstraint(
            "(execution_id IS NOT NULL) <> (external_scan_id IS NOT NULL)",
            name="ck_findings_single_origin",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    # Nullable because a finding can also come from an external scan (garak or
    # PyRIT); exactly one of this and external_scan_id is set.
    execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Set for findings ingested from a garak or PyRIT scan. CASCADE because the
    # findings are the scan's output: deleting the scan discards its results,
    # whereas deleting a target keeps the scan for history.
    external_scan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("external_scans.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    severity: Mapped[FindingSeverity] = mapped_column(
        SAEnum(
            FindingSeverity,
            name="finding_severity",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=FindingSeverity.MEDIUM,
        server_default=FindingSeverity.MEDIUM.value,
    )

    status: Mapped[FindingStatus] = mapped_column(
        SAEnum(
            FindingStatus,
            name="finding_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=FindingStatus.OPEN,
        server_default=FindingStatus.OPEN.value,
    )

    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Two-stage grading: the confirmation stage is separate from the
    # remediation lifecycle above. ``confirmation`` says whether the observed
    # attack result is real; ``status`` says what happened to it afterwards.
    confirmation: Mapped[FindingConfirmation] = mapped_column(
        SAEnum(
            FindingConfirmation,
            name="finding_confirmation",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=FindingConfirmation.CANDIDATE,
        server_default=FindingConfirmation.CANDIDATE.value,
        index=True,
    )

    # Who or what confirmed or dismissed the finding: ``judge`` for the
    # confirmation judge model, ``human`` for a reviewer in the UI/API.
    confirmation_source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Why the disposition was chosen, e.g. "judge: response refused" or a
    # reviewer's note. Kept alongside the state so a dismissal can be
    # audited rather than taken on faith.
    disposition_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confirmed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
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

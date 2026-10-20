"""Durable external scan job model for AegisAI.

An external scan wraps one garak or PyRIT run. Unlike a native execution, it can
take minutes and is executed by a separate runner process, so its state lives in
the database rather than in an in-process task registry.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExternalScanTool(StrEnum):
    """External scanners AegisAI can run."""

    GARAK = "garak"
    PYRIT = "pyrit"


class ExternalScanStatus(StrEnum):
    """Lifecycle state for an external scan job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExternalScan(Base):
    """A durable job for a garak or PyRIT run against a project target.

    The API is the only writer. A runner claims a job through the internal API,
    sets it running, and reports a terminal status. ``claimed_at`` is the lease
    marker: a claim older than the configured lease is treated as abandoned and
    requeued.
    """

    __tablename__ = "external_scans"
    __table_args__ = (
        # The claim query filters on status and orders by created_at. This one
        # index serves both the filter and the ordering, so claiming does not
        # degrade as terminal scans accumulate.
        Index(
            "ix_external_scans_status_created_at",
            "status",
            "created_at",
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

    # Nullable because targets use ON DELETE SET NULL, matching executions: the
    # scan record remains for history even if the target is removed.
    target_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("targets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    tool: Mapped[ExternalScanTool] = mapped_column(
        SAEnum(
            ExternalScanTool,
            name="external_scan_tool",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )

    tool_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    status: Mapped[ExternalScanStatus] = mapped_column(
        SAEnum(
            ExternalScanStatus,
            name="external_scan_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ExternalScanStatus.QUEUED,
        server_default=ExternalScanStatus.QUEUED.value,
    )

    external_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    report_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Lease marker. Set on claim, cleared on completion or cancellation.
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Per-claim nonce embedded in the scan's LLM token. A requeue mints a new
    # one, so a token kept by a runner whose scan has moved on is dead even
    # before its signature-derived expiry.
    claim_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Number of times this scan has been claimed. A requeued scan increments it
    # again, so a scan that keeps crashing its runner is visible rather than
    # silently looping forever.
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Number of model calls the LLM shim has forwarded for this scan. Counted
    # rather than audited per call: one UPDATE per request is far cheaper than
    # an audit row per probe attempt, and it still shows progress.
    forwarded_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

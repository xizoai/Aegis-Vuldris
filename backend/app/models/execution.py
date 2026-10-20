"""Execution job model for Aegis Vuldris."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExecutionStatus(StrEnum):
    """Lifecycle state for a security-test execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionResult(StrEnum):
    """Outcome of a completed execution's security test result.

    Distinguishes between the execution lifecycle (``ExecutionStatus``)
    and the semantic test result (whether the target behaved safely).

    ``NEEDS_REVIEW`` sits between ``FAIL`` and ``PASS``: the grader observed
    something suspicious (a candidate finding) but nothing has confirmed that
    the attack actually landed. Collapsing it into ``FAIL`` would report
    unverified matches as proven attacks; collapsing it into ``PASS`` would
    hide them. Only confirmed findings produce ``FAIL``.
    """

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NO_FINDINGS = "no_findings"
    NEEDS_REVIEW = "needs_review"


class Execution(Base):
    """A single run of a security test against a target."""

    __tablename__ = "executions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    test_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("security_tests.id", ondelete="SET NULL"),
        nullable=True,
    )

    target_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("targets.id", ondelete="SET NULL"),
        nullable=True,
    )

    # When set, this execution is a verification run: it re-executes the exact
    # security test that produced the referenced finding. A passed rerun is the
    # only path to ``FindingStatus.VERIFIED``; nothing else may set that state.
    verifies_finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(
            ExecutionStatus,
            name="execution_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ExecutionStatus.PENDING,
        server_default=ExecutionStatus.PENDING.value,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    result: Mapped[ExecutionResult] = mapped_column(
        SAEnum(
            ExecutionResult,
            name="execution_result",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ExecutionResult.INCONCLUSIVE,
        server_default=ExecutionResult.INCONCLUSIVE.value,
        index=True,
    )

    # Immutable snapshot of the target/model profile and the exact test
    # definition used for this run. The target row can be edited later, so a
    # result is only reproducible if the parameters that produced it travel
    # with the execution. Sensitive prompt content is represented by a digest,
    # not copied here.
    run_manifest: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
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

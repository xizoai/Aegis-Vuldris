"""Project database model for Aegis Vuldris."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Default evidence retention, in days.
#
# Evidence is the most sensitive data Aegis Vuldris holds: it contains the prompts
# sent and the responses that caused a finding. A bounded default means a
# project cannot silently keep it forever.
DEFAULT_EVIDENCE_RETENTION_DAYS = 90


class Project(Base):
    """A logical security-testing project and isolation boundary."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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

    # Optional: the target whose model grades this project's judge-model
    # tests. Kept separate from the target under test because a model that
    # grades its own answers is not an independent judge (ADR-005).
    #
    # SET NULL keeps target deletion working: deleting the judge target
    # disables judging (results become INCONCLUSIVE) rather than blocking
    # the delete or silently grading with an unrelated model.
    judge_target_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("targets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # How long evidence and report artifacts are kept for this project.
    #
    # 0 means keep indefinitely, which is only appropriate when the operator has
    # arranged their own deletion. Anything above 0 is enforced by
    # ``app.services.retention.cleanup_expired_evidence``.
    evidence_retention_days: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint(
            "evidence_retention_days >= 0",
            name="ck_project_evidence_retention_non_negative",
        ),
        nullable=False,
        default=DEFAULT_EVIDENCE_RETENTION_DAYS,
        server_default=str(DEFAULT_EVIDENCE_RETENTION_DAYS),
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

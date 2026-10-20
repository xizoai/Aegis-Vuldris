"""Candidate patch proposal model for Aegis Vuldris.

A patch proposal is a draft artifact attached to a finding. It is never an
applied change and never a fix state: a human marking a finding ``fixed``
records that something was applied, and only a passed verification rerun
marks it ``verified``. Proposals are immutable; a later draft for the same
finding is a new row, so no proposal can be edited into a claim.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatchProposalMode(StrEnum):
    """How a proposal's content was produced."""

    TEMPLATE = "template"
    LLM = "llm"


class PatchApproach(StrEnum):
    """Where the proposed change lives: usage, configuration, or code."""

    PROMPT_ENGINEERING = "prompt_engineering"
    CONFIG = "config"
    CODE = "code"
    MANUAL_REVIEW = "manual_review"


class PatchProposal(Base):
    """An immutable, review-only candidate change for a finding."""

    __tablename__ = "patch_proposals"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mode: Mapped[PatchProposalMode] = mapped_column(
        SAEnum(
            PatchProposalMode,
            name="patch_proposal_mode",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    approach: Mapped[PatchApproach] = mapped_column(
        SAEnum(
            PatchApproach,
            name="patch_approach",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    rationale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Unified diff text when a drafting model produced one. NULL in template
    # mode, which stays advisory on purpose rather than fabricating a diff
    # from a category template.
    diff_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    files_touched: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    # SHA-256 over the canonical drafting request (system + user messages).
    # Recorded so identical inputs can be shown to produce the same prompt,
    # and so a stored proposal can be tied to what the model actually saw.
    prompt_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    template_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    drafting_target_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("targets.id", ondelete="SET NULL"),
        nullable=True,
    )

    drafting_model: Mapped[str | None] = mapped_column(
        String(200),
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

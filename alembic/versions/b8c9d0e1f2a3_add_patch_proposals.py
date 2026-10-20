"""add candidate patch proposals

Candidate patch proposals are review-only drafts attached to findings. The
table is deliberately immutable: a proposal never carries the finding's fix
state, and ``diff_text`` is NULL for template-mode proposals, which stay
advisory rather than fabricating a diff. Applying a change and marking a
finding ``fixed`` remain human actions; only a passed verification rerun
marks a finding ``verified``.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-17 18:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


patch_proposal_mode_enum = postgresql.ENUM(
    "template",
    "llm",
    name="patch_proposal_mode",
)

patch_approach_enum = postgresql.ENUM(
    "prompt_engineering",
    "config",
    "code",
    "manual_review",
    name="patch_approach",
)


def upgrade() -> None:
    """Create the patch proposal table and its enums."""

    patch_proposal_mode_enum.create(op.get_bind(), checkfirst=True)
    patch_approach_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "patch_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column(
            "mode",
            postgresql.ENUM(
                "template",
                "llm",
                name="patch_proposal_mode",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "approach",
            postgresql.ENUM(
                "prompt_engineering",
                "config",
                "code",
                "manual_review",
                name="patch_approach",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=True),
        sa.Column(
            "files_touched",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("template_version", sa.String(length=50), nullable=True),
        sa.Column("drafting_target_id", sa.Uuid(), nullable=True),
        sa.Column("drafting_model", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["drafting_target_id"], ["targets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_patch_proposals_finding_id"),
        "patch_proposals",
        ["finding_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the patch proposal table and its enums."""

    op.drop_index(op.f("ix_patch_proposals_finding_id"), table_name="patch_proposals")
    op.drop_table("patch_proposals")
    patch_approach_enum.drop(op.get_bind(), checkfirst=True)
    patch_proposal_mode_enum.drop(op.get_bind(), checkfirst=True)

"""add evidence sensitivity, detected kinds, and redaction flag

Evidence was stored verbatim with no classification. A data-leakage finding
exists precisely because the model returned something sensitive, so the
response is the sensitive payload; storing it unlabelled left no way to apply
a different policy to restricted evidence.

These columns record what was detected and whether the content was redacted.
Existing rows default to INTERNAL with no detected kinds and redacted=0, which
is an honest description of rows written before this change.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-01 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Classify stored evidence."""

    op.add_column(
        "evidence",
        sa.Column(
            "sensitivity",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_check_constraint(
        "ck_evidence_sensitivity_range",
        "evidence",
        "sensitivity >= 0 AND sensitivity <= 3",
    )
    op.add_column(
        "evidence",
        sa.Column(
            "detected_kinds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "evidence",
        sa.Column(
            "redacted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        op.f("ix_evidence_sensitivity"),
        "evidence",
        ["sensitivity"],
        unique=False,
    )


def downgrade() -> None:
    """Remove evidence classification."""

    op.drop_index(op.f("ix_evidence_sensitivity"), table_name="evidence")
    op.drop_column("evidence", "redacted")
    op.drop_column("evidence", "detected_kinds")
    op.drop_constraint("ck_evidence_sensitivity_range", "evidence", type_="check")
    op.drop_column("evidence", "sensitivity")

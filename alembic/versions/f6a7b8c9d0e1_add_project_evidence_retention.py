"""add projects.evidence_retention_days

Evidence is the most sensitive data Aegis Vuldris holds. Retention was previously
unbounded, so a project accumulated evidence and generated artifacts forever.

The default is a bounded 90 days rather than "keep indefinitely" so that a
project cannot silently retain it without someone deciding to.

0 remains available for operators who arrange their own deletion.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-01 19:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the evidence retention window to projects."""

    op.add_column(
        "projects",
        sa.Column(
            "evidence_retention_days",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
    )
    op.create_check_constraint(
        "ck_project_evidence_retention_non_negative",
        "projects",
        "evidence_retention_days >= 0",
    )


def downgrade() -> None:
    """Remove the evidence retention window."""

    op.drop_constraint("ck_project_evidence_retention_non_negative", "projects", type_="check")
    op.drop_column("projects", "evidence_retention_days")

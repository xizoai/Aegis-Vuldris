"""add report versioning columns (version, data_path, generated_at)

Revision ID: b7c2d3e4f5a6
Revises: a6ad019ea4db
Create Date: 2026-09-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "a6ad019ea4db"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add report versioning columns.

    ``version`` counts how many times a report has been generated (0 means
    "never generated yet"). ``data_path`` points at a machine-readable JSON
    snapshot of the report data, which is what report-to-report comparison
    reads so that historical runs can be compared against each other even
    after the underlying findings have changed.
    """

    op.add_column(
        "reports",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "reports",
        sa.Column("data_path", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "reports",
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove report versioning columns."""

    op.drop_column("reports", "generated_at")
    op.drop_column("reports", "data_path")
    op.drop_column("reports", "version")

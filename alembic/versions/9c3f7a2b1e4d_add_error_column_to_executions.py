"""add error column to executions

Revision ID: 9c3f7a2b1e4d
Revises: 83d421e12258
Create Date: 2026-09-20 14:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c3f7a2b1e4d"
down_revision: str | Sequence[str] | None = "83d421e12258"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the error column to executions."""

    op.add_column("executions", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove the error column from executions."""

    op.drop_column("executions", "error")

"""add index on executions.result

Reconciles a pre-existing drift: the Execution.result column declared
``index=True`` in the model, but the migration that introduced the column
never created the index.

Revision ID: c3d4e5f6a7b8
Revises: b7c2d3e4f5a6
Create Date: 2026-09-27 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b7c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the missing index on executions.result."""

    op.create_index(
        op.f("ix_executions_result"),
        "executions",
        ["result"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the index on executions.result."""

    op.drop_index(op.f("ix_executions_result"), table_name="executions")

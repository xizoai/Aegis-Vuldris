"""add execution result and execution_steps table

Revision ID: a6ad019ea4db
Revises: 9c3f7a2b1e4d
Create Date: 2026-09-21 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a6ad019ea4db"
down_revision: str | Sequence[str] | None = "9c3f7a2b1e4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


execution_result_enum = postgresql.ENUM(
    "pass",
    "fail",
    "inconclusive",
    "no_findings",
    name="execution_result",
)


def upgrade() -> None:
    """Add result column to executions and create execution_steps table."""

    execution_result_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "executions",
        sa.Column(
            "result",
            postgresql.ENUM(
                "pass",
                "fail",
                "inconclusive",
                "no_findings",
                name="execution_result",
                create_type=False,
            ),
            nullable=False,
            server_default="inconclusive",
        ),
    )

    op.create_table(
        "execution_steps",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "execution_id",
            sa.UUID(),
            sa.ForeignKey("executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "request_content",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("response_output", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        op.f("ix_execution_steps_execution_id"),
        "execution_steps",
        ["execution_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove execution_steps table and result column from executions."""

    op.drop_index(
        op.f("ix_execution_steps_execution_id"),
        table_name="execution_steps",
    )
    op.drop_table("execution_steps")

    op.drop_column("executions", "result")
    execution_result_enum.drop(op.get_bind(), checkfirst=True)

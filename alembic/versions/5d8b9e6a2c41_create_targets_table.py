"""create targets table

Revision ID: 5d8b9e6a2c41
Revises: 31ad5d58405d
Create Date: 2026-09-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "5d8b9e6a2c41"
down_revision: str | Sequence[str] | None = "31ad5d58405d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


target_provider_enum = postgresql.ENUM(
    "openai_compatible",
    "ollama",
    "custom_rest",
    name="target_provider",
)

target_status_enum = postgresql.ENUM(
    "active",
    "inactive",
    name="target_status",
)


def upgrade() -> None:
    """Create the target configuration table."""

    target_provider_enum.create(op.get_bind(), checkfirst=True)
    target_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "provider",
            postgresql.ENUM(
                "openai_compatible",
                "ollama",
                "custom_rest",
                name="target_provider",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column(
            "capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "timeout_seconds",
            sa.Float(),
            server_default=sa.text("30.0"),
            nullable=False,
        ),
        sa.Column(
            "rate_limit_per_minute",
            sa.Integer(),
            server_default=sa.text("60"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "inactive",
                name="target_status",
                create_type=False,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("timeout_seconds > 0", name="ck_targets_timeout_seconds_positive"),
        sa.CheckConstraint(
            "rate_limit_per_minute > 0", name="ck_targets_rate_limit_per_minute_positive"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_targets_project_id"), "targets", ["project_id"], unique=False)
    op.create_index(op.f("ix_targets_provider"), "targets", ["provider"], unique=False)
    op.create_index(op.f("ix_targets_status"), "targets", ["status"], unique=False)


def downgrade() -> None:
    """Drop the target configuration table."""

    op.drop_index(op.f("ix_targets_status"), table_name="targets")
    op.drop_index(op.f("ix_targets_provider"), table_name="targets")
    op.drop_index(op.f("ix_targets_project_id"), table_name="targets")
    op.drop_table("targets")

    target_status_enum.drop(op.get_bind(), checkfirst=True)
    target_provider_enum.drop(op.get_bind(), checkfirst=True)

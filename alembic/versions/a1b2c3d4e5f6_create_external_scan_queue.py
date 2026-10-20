"""create external scan queue

External scans run in a separate runner and outlive the API process, so their
state is durable. The runner claims work with ``FOR UPDATE SKIP LOCKED`` (see
``app/services/scans.py``), which is why status and created_at share an index:
claiming filters on status and orders by created_at.

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-10-18 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


external_scan_tool_enum = postgresql.ENUM(
    "garak",
    "pyrit",
    name="external_scan_tool",
)

external_scan_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="external_scan_status",
)


def upgrade() -> None:
    """Create the durable external scan queue."""

    external_scan_tool_enum.create(op.get_bind(), checkfirst=True)
    external_scan_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "external_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column(
            "tool",
            postgresql.ENUM(
                "garak",
                "pyrit",
                name="external_scan_tool",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("tool_version", sa.String(length=100), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="external_scan_status",
                create_type=False,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("external_run_id", sa.String(length=255), nullable=True),
        sa.Column("report_path", sa.String(length=1024), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["targets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_external_scans_project_id"),
        "external_scans",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_scans_target_id"),
        "external_scans",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_scans_tool"),
        "external_scans",
        ["tool"],
        unique=False,
    )
    op.create_index(
        "ix_external_scans_status_created_at",
        "external_scans",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the durable external scan queue."""

    op.drop_index("ix_external_scans_status_created_at", table_name="external_scans")
    op.drop_index(op.f("ix_external_scans_tool"), table_name="external_scans")
    op.drop_index(op.f("ix_external_scans_target_id"), table_name="external_scans")
    op.drop_index(op.f("ix_external_scans_project_id"), table_name="external_scans")
    op.drop_table("external_scans")

    external_scan_status_enum.drop(op.get_bind(), checkfirst=True)
    external_scan_tool_enum.drop(op.get_bind(), checkfirst=True)

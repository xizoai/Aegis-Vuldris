"""add target credentials

Revision ID: 62d590dea9e3
Revises: 5d8b9e6a2c41
Create Date: 2026-09-19 21:47:32.062241

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "62d590dea9e3"
down_revision: str | Sequence[str] | None = "5d8b9e6a2c41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the target credentials table."""

    op.create_table(
        "target_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("credential_type", sa.String(length=50), nullable=False),
        sa.Column("encrypted_value", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.CheckConstraint("version > 0", name="ck_target_credentials_version_positive"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_id",
            "credential_type",
            "version",
            name="uq_target_credentials_target_type_version",
        ),
    )
    op.create_index(
        op.f("ix_target_credentials_target_id"),
        "target_credentials",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_target_credentials_revoked"),
        "target_credentials",
        ["revoked"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the target credentials table."""

    op.drop_index(op.f("ix_target_credentials_revoked"), table_name="target_credentials")
    op.drop_index(op.f("ix_target_credentials_target_id"), table_name="target_credentials")
    op.drop_table("target_credentials")

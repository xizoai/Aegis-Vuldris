"""add authorization attestation columns to targets

Revision ID: 5c212298f022
Revises: c3d4e5f6a7b8
Create Date: 2026-09-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5c212298f022"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add authorization attestation columns to targets.

    Nullable because existing targets created before this migration were
    never asked to attest; the TargetCreate schema requires attestation
    (``Literal[True]``) for every new target going forward, so new rows
    always populate these columns.
    """

    op.add_column(
        "targets",
        sa.Column("authorization_attested_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "targets",
        sa.Column(
            "authorization_attested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_targets_authorization_attested_by"),
        "targets",
        ["authorization_attested_by"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_targets_authorization_attested_by_users",
        "targets",
        "users",
        ["authorization_attested_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove authorization attestation columns from targets."""

    op.drop_constraint(
        "fk_targets_authorization_attested_by_users",
        "targets",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_targets_authorization_attested_by"),
        table_name="targets",
    )
    op.drop_column("targets", "authorization_attested_at")
    op.drop_column("targets", "authorization_attested_by")

"""add finding verification state and execution verification link

A finding's lifecycle now separates a human claim from deterministic evidence:
``fixed`` means a person says a change was applied, ``verified`` means the exact
attack was re-run and no longer reproduces. Only a passed verification
execution sets ``verified``; the API rejects it as an editable status, so a
generated suggestion can never be mistaken for a proven fix.

The verification link lives on ``executions`` (the rerun) rather than on the
finding, so a finding can be re-verified over time and every attempt remains
visible as an execution with its own status, result, and evidence.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-17 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the verified state and the verification link, both additive."""

    # Safe inside a transaction on PostgreSQL 12+: the new value is only
    # selected by later transactions, never within this one.
    op.execute("ALTER TYPE finding_status ADD VALUE IF NOT EXISTS 'verified'")

    op.add_column(
        "executions",
        sa.Column("verifies_finding_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_executions_verifies_finding_id"),
        "executions",
        ["verifies_finding_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_executions_verifies_finding_id_findings",
        "executions",
        "findings",
        ["verifies_finding_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove the verification link.

    The ``verified`` enum value is left in place: PostgreSQL cannot drop a
    value from an existing enum without rebuilding the type, and an unused
    value is harmless.
    """

    op.drop_constraint(
        "fk_executions_verifies_finding_id_findings", "executions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_executions_verifies_finding_id"), table_name="executions")
    op.drop_column("executions", "verifies_finding_id")

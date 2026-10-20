"""let findings come from an external scan

Phase 2 ingests garak verdicts as findings. A scan finding has no execution to
hang off, so ``findings.execution_id`` becomes nullable and a second origin
column, ``external_scan_id``, is added; a check constraint keeps it to exactly
one of the two. Without that constraint a later reader has to guess which
origin owns a row, and a bug that sets neither would only show up as a broken
join.

Revision ID: c4d9e1f2a3b5
Revises: b2c8e4f5d1a7
Create Date: 2026-10-18 05:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d9e1f2a3b5"
down_revision: str | Sequence[str] | None = "b2c8e4f5d1a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the external-scan origin for findings."""

    op.alter_column(
        "findings",
        "execution_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column(
        "findings",
        sa.Column("external_scan_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_findings_external_scan_id",
        "findings",
        "external_scans",
        ["external_scan_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_findings_external_scan_id"),
        "findings",
        ["external_scan_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_findings_single_origin",
        "findings",
        "(execution_id IS NOT NULL) <> (external_scan_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Return findings to a native-execution-only origin."""

    op.drop_constraint("ck_findings_single_origin", "findings", type_="check")
    op.drop_index(op.f("ix_findings_external_scan_id"), table_name="findings")
    op.drop_constraint(
        "fk_findings_external_scan_id",
        "findings",
        type_="foreignkey",
    )
    op.drop_column("findings", "external_scan_id")
    # Scan-derived findings have no execution to fall back on. Restoring NOT
    # NULL would fail on them, so the downgrade discards them; the raw tool
    # report remains on disk if it was retained.
    op.execute("DELETE FROM findings WHERE execution_id IS NULL")
    op.alter_column(
        "findings",
        "execution_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

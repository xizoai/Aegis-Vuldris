"""add finding confirmation and needs_review result

Two-stage grading needs a place to record the confirmation stage and a
result that means "something was observed but nothing is established yet".

``findings.confirmation`` separates the trust question ("did the attack
actually land?") from the remediation lifecycle in ``findings.status``. It
defaults to ``candidate`` because the deterministic grader is lexical: a
pattern match is reproducible, but a substring rule matching a refusal's
echo of the attack's wording is not proof of a vulnerability. A judge model
or a human reviewer moves it to ``confirmed`` or ``dismissed``.

``execution_result.needs_review`` is the verdict for a run whose findings
are all still candidates. It cannot be ``fail`` (nothing is confirmed) and
must not be ``pass`` (something was observed): hiding either one would
either overstate the evidence or bury it.

Revision ID: d7e8f9a0b1c2
Revises: c9d0e1f2a3b4
Create Date: 2026-10-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the confirmation lifecycle and the needs_review execution result.

    ``ALTER TYPE ... ADD VALUE`` runs in an autocommit block: the new enum
    label may not be used in the same transaction that adds it, so it is
    committed before the column work begins.
    """

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE execution_result ADD VALUE IF NOT EXISTS 'needs_review'")

    op.execute("CREATE TYPE finding_confirmation AS ENUM ('candidate', 'confirmed', 'dismissed')")
    confirmation = postgresql.ENUM(
        "candidate",
        "confirmed",
        "dismissed",
        name="finding_confirmation",
        create_type=False,
    )
    op.add_column(
        "findings",
        sa.Column(
            "confirmation",
            confirmation,
            nullable=False,
            server_default="candidate",
        ),
    )
    op.create_index(
        op.f("ix_findings_confirmation"),
        "findings",
        ["confirmation"],
        unique=False,
    )
    op.add_column(
        "findings",
        sa.Column("confirmation_source", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("disposition_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_findings_confirmed_by_users",
        "findings",
        "users",
        ["confirmed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "findings",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove the confirmation columns.

    The ``needs_review`` label cannot be removed from a PostgreSQL enum in
    place, so the downgrade leaves it defined. Rows that already use it must
    be re-graded before the label is deleted by hand; silently coercing them
    to another result would misstate their evidence.
    """

    op.drop_column("findings", "confirmed_at")
    op.drop_constraint(
        "fk_findings_confirmed_by_users",
        "findings",
        type_="foreignkey",
    )
    op.drop_column("findings", "confirmed_by")
    op.drop_column("findings", "disposition_reason")
    op.drop_column("findings", "confirmation_source")
    op.drop_index(op.f("ix_findings_confirmation"), table_name="findings")
    op.drop_column("findings", "confirmation")
    op.execute("DROP TYPE finding_confirmation")

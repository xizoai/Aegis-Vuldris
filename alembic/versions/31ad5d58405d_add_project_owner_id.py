"""add project owner identifier

Revision ID: 31ad5d58405d
Revises: 12e10481be79
Create Date: 2026-09-18 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31ad5d58405d"
down_revision: str | Sequence[str] | None = "12e10481be79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable project owner foreign key."""

    op.add_column(
        "projects",
        sa.Column("owner_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_projects_owner_id"),
        "projects",
        ["owner_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_projects_owner_id_users",
        "projects",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove the project owner foreign key."""

    op.drop_constraint(
        "fk_projects_owner_id_users",
        "projects",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_column("projects", "owner_id")

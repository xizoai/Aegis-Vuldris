"""merge finding confirmation and external scan heads

The trust work (finding confirmation, ``needs_review``) and the external scan
queue landed on separate branches, each adding its own Alembic revision. The
schema changes do not overlap; this merge revision joins the two lines so a
single ``alembic upgrade head`` applies both.

Revision ID: 6656f2e575e2
Revises: c4d9e1f2a3b5, d7e8f9a0b1c2
Create Date: 2026-10-19 19:00:54.128765

"""

from collections.abc import Sequence

revision: str = "6656f2e575e2"
down_revision: str | Sequence[str] | None = ("c4d9e1f2a3b5", "d7e8f9a0b1c2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge point only: both parent revisions own the actual schema changes."""


def downgrade() -> None:
    """Merge point only: downgrading one parent leaves the other in place."""

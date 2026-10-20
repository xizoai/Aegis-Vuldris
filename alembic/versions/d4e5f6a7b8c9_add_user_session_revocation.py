"""add users.session_version for session revocation

Access tokens are stateless JWTs, so a token remained usable until it expired.
This column records a monotonic session counter: each token carries the version
it was minted with, signing out increments the counter, and any token minted
under an older version is rejected.

A counter rather than a timestamp cut-off because JWT ``iat`` only has second
granularity, which leaves an ambiguous same-second case where either sign-out
silently fails or a fresh sign-in is wrongly rejected.

Non-null with a zero default so existing accounts keep working.

Revision ID: d4e5f6a7b8c9
Revises: 5c212298f022
Create Date: 2026-10-01 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "5c212298f022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the session version counter to users."""

    op.add_column(
        "users",
        sa.Column(
            "session_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Remove the session version counter."""

    op.drop_column("users", "session_version")

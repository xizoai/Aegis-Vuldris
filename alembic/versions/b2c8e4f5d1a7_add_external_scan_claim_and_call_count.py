"""add external scan claim nonce and call counter

The LLM shim (phase 1) mints a scan-scoped token at claim time. The token
embeds a per-claim nonce: a scan that is requeued gets a fresh nonce, so a
token kept by a runner whose attempt is over dies immediately instead of
remaining valid until its signature-derived expiry.

The forwarded-request counter is the shim's volume surface. It is counted per
scan rather than audited per call -- one UPDATE per forwarded request is far
cheaper than an audit row per probe attempt, and no prompt or response body
ever lands in a log.

Revision ID: b2c8e4f5d1a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-18 04:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c8e4f5d1a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the claim nonce and forwarded-request counter."""

    op.add_column(
        "external_scans",
        sa.Column("claim_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "external_scans",
        sa.Column(
            "forwarded_requests",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop the claim nonce and forwarded-request counter."""

    op.drop_column("external_scans", "forwarded_requests")
    op.drop_column("external_scans", "claim_id")

"""add model profile to targets and run manifest to executions

A model name is not a model version. Providers update the weights behind the
same identifier, so a security result is not reproducible unless the run
records the declared revision and the generation settings that produced it.

``targets`` gains an optional model profile: a version/revision string, a
target-level system prompt, and generation defaults. A test case's explicit
values still win over these defaults; the profile fills the gaps.

``executions.run_manifest`` stores an immutable JSON snapshot of the effective
target profile and test definition at the moment the run starts. It is nullable
because executions created before this migration have no snapshot.

Revision ID: a3f4b5c6d7e8
Revises: 6656f2e575e2
Create Date: 2026-10-19 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3f4b5c6d7e8"
down_revision: str | Sequence[str] | None = "6656f2e575e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the target model profile and execution run manifest."""

    op.add_column("targets", sa.Column("model_version", sa.String(length=255), nullable=True))
    op.add_column("targets", sa.Column("system_prompt", sa.Text(), nullable=True))
    op.add_column("targets", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("targets", sa.Column("top_p", sa.Float(), nullable=True))
    op.add_column("targets", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("targets", sa.Column("seed", sa.Integer(), nullable=True))

    op.create_check_constraint(
        "ck_targets_temperature_range",
        "targets",
        "temperature IS NULL OR (temperature >= 0 AND temperature <= 2)",
    )
    op.create_check_constraint(
        "ck_targets_top_p_range",
        "targets",
        "top_p IS NULL OR (top_p >= 0 AND top_p <= 1)",
    )
    op.create_check_constraint(
        "ck_targets_max_tokens_positive",
        "targets",
        "max_tokens IS NULL OR max_tokens > 0",
    )
    op.create_check_constraint(
        "ck_targets_seed_nonnegative",
        "targets",
        "seed IS NULL OR seed >= 0",
    )

    op.add_column(
        "executions",
        sa.Column("run_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Remove the run manifest and target model profile."""

    op.drop_column("executions", "run_manifest")

    op.drop_constraint("ck_targets_seed_nonnegative", "targets", type_="check")
    op.drop_constraint("ck_targets_max_tokens_positive", "targets", type_="check")
    op.drop_constraint("ck_targets_top_p_range", "targets", type_="check")
    op.drop_constraint("ck_targets_temperature_range", "targets", type_="check")

    op.drop_column("targets", "seed")
    op.drop_column("targets", "max_tokens")
    op.drop_column("targets", "top_p")
    op.drop_column("targets", "temperature")
    op.drop_column("targets", "system_prompt")
    op.drop_column("targets", "model_version")

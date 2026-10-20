"""add project judge target

The model that grades judge-model tests is a project-level choice, kept
separate from the target under test so a model never judges its own answers
(ADR-005: an LLM judge must remain logically separate from the target model).
``judge_target_id`` is nullable because judge-model grading is opt-in; a
project without a judge target returns INCONCLUSIVE for those tests instead of
grading with whichever model happens to be around.

``ON DELETE SET NULL`` keeps target deletion working: deleting the judge
target disables judging (the honest INCONCLUSIVE), rather than blocking the
delete or leaving a dangling reference.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-17 20:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable judge-target reference to projects."""

    op.add_column(
        "projects",
        sa.Column("judge_target_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_projects_judge_target_id"),
        "projects",
        ["judge_target_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_projects_judge_target_id_targets",
        "projects",
        "targets",
        ["judge_target_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove the project judge-target reference."""

    op.drop_constraint(
        "fk_projects_judge_target_id_targets",
        "projects",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_projects_judge_target_id"), table_name="projects")
    op.drop_column("projects", "judge_target_id")

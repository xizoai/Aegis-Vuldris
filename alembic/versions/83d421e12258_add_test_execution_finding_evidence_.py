"""add security tests, executions, findings, evidence, and reports

Revision ID: 83d421e12258
Revises: 542be6fadd8d
Create Date: 2026-09-20 17:15:19.784590

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "83d421e12258"
down_revision: str | Sequence[str] | None = "542be6fadd8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


execution_status_enum = postgresql.ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    name="execution_status",
)

finding_severity_enum = postgresql.ENUM(
    "info",
    "low",
    "medium",
    "high",
    "critical",
    name="finding_severity",
)

finding_status_enum = postgresql.ENUM(
    "open",
    "in_progress",
    "fixed",
    "wont_fix",
    name="finding_status",
)


def upgrade() -> None:
    """Create the assessment domain tables."""

    execution_status_enum.create(op.get_bind(), checkfirst=True)
    finding_severity_enum.create(op.get_bind(), checkfirst=True)
    finding_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "security_tests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column(
            "required_capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_security_tests_project_id"), "security_tests", ["project_id"], unique=False
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                name="execution_status",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_id"], ["security_tests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_executions_project_id"), "executions", ["project_id"], unique=False)
    op.create_index(op.f("ix_executions_status"), "executions", ["status"], unique=False)

    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "severity",
            postgresql.ENUM(
                "info",
                "low",
                "medium",
                "high",
                "critical",
                name="finding_severity",
                create_type=False,
            ),
            server_default="medium",
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "open",
                "in_progress",
                "fixed",
                "wont_fix",
                name="finding_status",
                create_type=False,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_findings_execution_id"), "findings", ["execution_id"], unique=False)

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidence_finding_id"), "evidence", ["finding_id"], unique=False)

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False, server_default="json"),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_project_id"), "reports", ["project_id"], unique=False)


def downgrade() -> None:
    """Drop the assessment domain tables."""

    op.drop_index(op.f("ix_reports_project_id"), table_name="reports")
    op.drop_table("reports")

    op.drop_index(op.f("ix_evidence_finding_id"), table_name="evidence")
    op.drop_table("evidence")

    op.drop_index(op.f("ix_findings_execution_id"), table_name="findings")
    op.drop_table("findings")

    op.drop_index(op.f("ix_executions_status"), table_name="executions")
    op.drop_index(op.f("ix_executions_project_id"), table_name="executions")
    op.drop_table("executions")

    op.drop_index(op.f("ix_security_tests_project_id"), table_name="security_tests")
    op.drop_table("security_tests")

    finding_status_enum.drop(op.get_bind(), checkfirst=True)
    finding_severity_enum.drop(op.get_bind(), checkfirst=True)
    execution_status_enum.drop(op.get_bind(), checkfirst=True)

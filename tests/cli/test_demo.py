"""Offline demo seeding tests: the honesty rules for demo data.

The demo exists so a new user can explore the UI with zero provider
credentials. That only works if the data is unmistakably synthetic and can
never masquerade as a real assessment result: every row carries a ``[DEMO]``
marker, finding statuses stay un-resolved (never ``fixed``, never
``verified``; attaching evidence moves them to ``in_progress``), their
confirmation is the recorded fixture verdict, and seeding is idempotent so
re-running the command never duplicates a project.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from app.cli import main as cli_main
from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.evidence import Evidence
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.execution_step import ExecutionStep
from app.models.finding import Finding, FindingConfirmation, FindingStatus
from app.models.project import Project
from app.models.target import Target
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas import UserCreate
from app.services.auth import register_user
from app.services.demo import (
    DEFAULT_DEMO_PROJECT_NAME,
    DEMO_MARKER,
    seed_demo_project,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def _register_user(session: Session) -> User:
    return register_user(
        session,
        UserCreate(email=f"demo-{uuid4()}@example.com", password="a-very-strong-password-123"),
    )


@pytest.fixture
def session() -> Iterator[Session]:
    session = create_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _project_rows(session: Session, project_id) -> tuple[Project, Target, SecurityTest, Execution]:
    project = session.get(Project, project_id)
    target = session.scalar(select(Target).where(Target.project_id == project_id))
    test = session.scalar(select(SecurityTest).where(SecurityTest.project_id == project_id))
    execution = session.scalar(select(Execution).where(Execution.project_id == project_id))
    assert project is not None and target is not None
    assert test is not None and execution is not None
    return project, target, test, execution


def test_demo_seed_creates_a_fully_marked_synthetic_project(session: Session) -> None:
    user = _register_user(session)
    report = seed_demo_project(session, user)
    assert report.created is True

    project, target, test, execution = _project_rows(session, report.project_id)

    # Every visible row carries the marker and says it is a recording.
    assert project.name.startswith(DEMO_MARKER)
    assert "synthetic" in (project.description or "").lower()
    assert target.name.startswith(DEMO_MARKER)
    assert target.endpoint == "https://demo.invalid/v1"
    assert test.name.startswith(DEMO_MARKER)
    assert (test.config or {}).get("grading", {}).get("title", "").startswith(DEMO_MARKER)

    # The execution is a recording of the fixture outcome, not a live run.
    assert execution.status == ExecutionStatus.SUCCEEDED
    assert execution.result == ExecutionResult.FAIL
    steps = list(
        session.scalars(
            select(ExecutionStep).where(ExecutionStep.execution_id == execution.id)
        ).all()
    )
    assert len(steps) == 1
    assert (
        steps[0]
        .request_content["messages"][0]["content"]
        .startswith("Ignore all previous instructions")
    )
    assert "system prompt" in (steps[0].response_output or "")

    # Findings stay open — never fixed, never verified — with [DEMO] titles and
    # synthetic metadata. They are seeded confirmed because the recorded result
    # is `fail`: under two-stage grading a candidate would make it
    # `needs_review`, and the confirmation source says the fixture decided it,
    # not a person or a judge.
    findings = list(
        session.scalars(select(Finding).where(Finding.execution_id == execution.id)).all()
    )
    assert len(findings) == report.findings
    for finding in findings:
        assert finding.title.startswith(DEMO_MARKER)
        assert finding.status not in (FindingStatus.FIXED, FindingStatus.VERIFIED)
        assert finding.confirmation == FindingConfirmation.CONFIRMED
        assert finding.confirmation_source == "demo-fixture"
        assert finding.details.get("synthetic") is True

    evidence = list(
        session.scalars(
            select(Evidence).where(Evidence.finding_id.in_([f.id for f in findings]))
        ).all()
    )
    assert len(evidence) == report.evidence
    for row in evidence:
        assert (row.description or "").startswith(DEMO_MARKER)
        assert "request" in row.content and "response" in row.content

    seeded = session.scalars(select(AuditLog).where(AuditLog.action == "demo.seeded")).all()
    assert any(str(report.project_id) in str(entry.resource_id) for entry in seeded)


def test_demo_seed_is_idempotent_per_account(session: Session) -> None:
    user = _register_user(session)
    first = seed_demo_project(session, user)
    second = seed_demo_project(session, user)

    assert second.created is False
    assert second.project_id == first.project_id
    assert second.findings == first.findings

    executions = list(
        session.scalars(select(Execution).where(Execution.project_id == first.project_id)).all()
    )
    assert len(executions) == 1, "a second seed must not duplicate recorded executions"


def test_demo_seed_scopes_to_the_owning_account(session: Session) -> None:
    first_user = _register_user(session)
    second_user = _register_user(session)
    first = seed_demo_project(session, first_user)
    second = seed_demo_project(session, second_user)

    assert second.created is True
    assert second.project_id != first.project_id


def test_demo_prune_deletes_only_the_demo_project(session: Session) -> None:
    from app.services.demo import prune_demo_project

    user = _register_user(session)
    report = seed_demo_project(session, user)
    assert prune_demo_project(session, user, project_name=DEFAULT_DEMO_PROJECT_NAME) is True
    assert session.get(Project, report.project_id) is None
    assert prune_demo_project(session, user, project_name=DEFAULT_DEMO_PROJECT_NAME) is False


def _demo_project_for(session: Session, user: User) -> Project | None:
    return session.scalar(
        select(Project).where(
            Project.owner_id == user.id,
            Project.name == DEFAULT_DEMO_PROJECT_NAME,
        )
    )


def test_demo_cli_seeds_prunes_and_dry_runs(
    capsys: pytest.CaptureFixture[str], session: Session
) -> None:
    user = _register_user(session)

    # Dry-run writes nothing.
    assert cli_main.main(["demo", "--email", user.email, "--dry-run"]) == 0
    assert "would seed" in capsys.readouterr().out
    assert _demo_project_for(session, user) is None

    assert cli_main.main(["demo", "--email", user.email]) == 0
    output = capsys.readouterr().out
    assert "seeded demo project" in output
    assert _demo_project_for(session, user) is not None

    # Idempotent through the CLI too.
    assert cli_main.main(["demo", "--email", user.email]) == 0
    assert "already seeded" in capsys.readouterr().out

    assert cli_main.main(["demo", "--email", user.email, "--prune"]) == 0
    assert "deleted demo project" in capsys.readouterr().out
    session.expire_all()
    assert _demo_project_for(session, user) is None


def test_demo_cli_requires_an_existing_account(
    capsys: pytest.CaptureFixture[str], session: Session
) -> None:
    assert cli_main.main(["demo", "--email", "nobody@example.com"]) == 1
    assert "no account" in capsys.readouterr().err

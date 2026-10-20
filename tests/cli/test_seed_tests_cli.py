"""Tests for the seed_tests CLI entry point."""

from uuid import uuid4

import pytest
from app.cli.seed_tests import main
from app.db.session import create_session_factory
from app.models.test import SecurityTest
from app.schemas import ProjectCreate, UserCreate
from app.services.auth import register_user
from app.services.projects import create_project
from sqlalchemy import select
from sqlalchemy.orm import Session


def _session() -> Session:
    return create_session_factory()()


def _project(session: Session, email: str | None = None):
    email = email or f"cli-{uuid4()}@example.com"
    owner = register_user(
        session,
        UserCreate(email=email, password="a-very-strong-password"),
    )
    project = create_project(
        session,
        ProjectCreate(name=f"CLI {uuid4()}"),
        owner_id=owner.id,
    )
    return owner, project, email


def test_cli_rejects_unknown_project(capsys) -> None:
    assert main(["--project", str(uuid4()), "--email", "nobody@example.com"]) == 1
    assert "not found" in capsys.readouterr().err


def test_cli_rejects_unknown_email(capsys) -> None:
    session = _session()
    owner, project, _ = _project(session)
    try:
        code = main(["--project", str(project.id), "--email", "ghost@example.com"])
        assert code == 1
        assert "no user with email" in capsys.readouterr().err
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cli_rejects_unknown_category(capsys) -> None:
    session = _session()
    owner, project, email = _project(session)
    try:
        # argparse rejects invalid choices before touching the database.
        with pytest.raises(SystemExit) as exc:
            main(
                [
                    "--project",
                    str(project.id),
                    "--email",
                    email,
                    "--category",
                    "not_a_category",
                ]
            )
        assert exc.value.code == 2
        assert "invalid choice" in capsys.readouterr().err
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cli_dry_run_creates_nothing(capsys) -> None:
    session = _session()
    owner, project, email = _project(session)
    try:
        code = main(
            [
                "--project",
                str(project.id),
                "--email",
                email,
                "--dry-run",
                "--limit",
                "3",
            ]
        )
        assert code == 0
        assert "would create 3" in capsys.readouterr().out

        rows = session.scalars(
            select(SecurityTest).where(SecurityTest.project_id == project.id)
        ).all()
        assert list(rows) == []
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cli_seeds_and_prunes() -> None:
    session = _session()
    owner, project, email = _project(session)
    try:
        code = main(
            [
                "--project",
                str(project.id),
                "--email",
                email,
                "--category",
                "prompt_injection",
                "--limit",
                "4",
            ]
        )
        assert code == 0

        rows = list(
            session.scalars(select(SecurityTest).where(SecurityTest.project_id == project.id)).all()
        )
        assert len(rows) == 4
        assert all(row.config["category"] == "prompt_injection" for row in rows)

        # Running again with the same limit is a no-op.
        second = main(
            [
                "--project",
                str(project.id),
                "--email",
                email,
                "--category",
                "prompt_injection",
                "--limit",
                "4",
            ]
        )
        assert second == 0
        session.expire_all()
        rows = list(
            session.scalars(select(SecurityTest).where(SecurityTest.project_id == project.id)).all()
        )
        assert len(rows) == 4

        # Prune removes them.
        assert main(["--project", str(project.id), "--email", email, "--prune"]) == 0
        session.expire_all()
        rows = list(
            session.scalars(select(SecurityTest).where(SecurityTest.project_id == project.id)).all()
        )
        assert rows == []
    finally:
        session.delete(project)
        session.commit()
        session.close()

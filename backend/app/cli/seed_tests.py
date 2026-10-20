"""``python -m app.cli.seed_tests`` — load the attack library into a project.

The bundled YAML test cases are the canonical attack library, but they are
static files. Until they are imported into the database a project has no tests
and no execution can be run. This command performs that import.

Usage:
    python -m app.cli.seed_tests --project <uuid> --email owner@example.com

Options:
    --project UUID    Project to seed (required)
    --email EMAIL    Owner account the tests are attributed to (required)
    --category NAME  Limit to one category; repeatable
    --dir PATH       Override the test case directory
    --prune          Delete this project's tests and exit
    --dry-run        Report what would change without writing
    --limit N        Cap the number of tests created (useful for demos)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.db.session import create_session_factory
from app.models.project import Project
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas.test_case import TestCaseCategory
from app.services.seed_tests import (
    DEFAULT_TEST_CASE_DIR,
    existing_test_names,
    seed_project_tests,
)
from app.services.test_cases import load_test_cases_from_dir


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.seed_tests",
        description="Seed a project with the bundled security test cases.",
    )
    parser.add_argument(
        "--project",
        required=True,
        type=UUID,
        help="Project ID to seed.",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email of the user the created tests are attributed to.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_TEST_CASE_DIR,
        help="Test case directory (defaults to the bundled library).",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        choices=[c.value for c in TestCaseCategory],
        help="Limit to a category. Repeatable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Create at most this many tests.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete every test in the project and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing.",
    )
    return parser.parse_args(argv)


def _load_cases(directory: Path, categories: set[TestCaseCategory]) -> list:
    cases = load_test_cases_from_dir(directory)
    if categories:
        cases = [case for case in cases if case.category in categories]
    return cases


def _print_preview(cases: list, existing: set[str], limit: int | None) -> None:
    pending = [case for case in cases if case.name not in existing]
    if limit is not None:
        pending = pending[:limit]
    print(f"would create {len(pending)} of {len(cases)} test cases")
    for case in pending[:10]:
        print(f"  + {case.name}")
    if len(pending) > 10:
        print(f"  ... and {len(pending) - 10} more")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""

    args = _parse_args(argv)
    session = create_session_factory()()

    try:
        project = session.get(Project, args.project)
        if project is None:
            print(f"error: project {args.project} not found", file=sys.stderr)
            return 1

        user = session.scalar(select(User).where(User.email == args.email))
        if user is None:
            print(f"error: no user with email {args.email!r}", file=sys.stderr)
            return 1

        categories = {TestCaseCategory(value) for value in args.category}

        if args.prune:
            rows = list(
                session.scalars(
                    select(SecurityTest).where(SecurityTest.project_id == project.id)
                ).all()
            )
            if args.dry_run:
                print(f"would delete {len(rows)} tests from {project.name!r}")
                return 0
            for row in rows:
                session.delete(row)
            session.commit()
            print(f"deleted {len(rows)} tests from {project.name!r}")
            return 0

        if args.dry_run:
            cases = _load_cases(args.dir, categories)
            _print_preview(cases, existing_test_names(session, project.id), args.limit)
            return 0

        report = seed_project_tests(
            session,
            project.id,
            user,
            test_case_dir=args.dir,
            categories=categories or None,
            limit=args.limit,
        )

        print(f"seeded {project.name!r}: {report.summary()}")
        for name in report.created:
            print(f"  + {name}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())

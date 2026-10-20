"""Seed a project with the bundled security test case library.

The YAML files under ``app/test_cases`` are the canonical attack library, but
nothing imports them into the database, so a freshly created project has no
tests and the execution engine cannot be used. This service bridges that gap by
converting the files into ``SecurityTest`` rows.

The conversion is deliberately thin: ``TestCase.to_config()`` already produces
the dict shape the execution engine reads, so the only work here is wrapping it
in a row and adding the ``category`` key that report generation relies on for
OWASP mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ProjectNotFoundError
from app.models.project import Project
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas.assessment import SecurityTestCreate
from app.schemas.test_case import TestCase, TestCaseCategory
from app.services.assessments import create_security_test
from app.services.attack_plugins import AttackPlugin
from app.services.projects import ensure_project_access
from app.services.test_cases import load_test_cases_from_dir

# Bundled library location, resolved relative to the installed package so the
# CLI works from any working directory.
DEFAULT_TEST_CASE_DIR = Path(__file__).resolve().parent.parent / "test_cases"


@dataclass
class SeedReport:
    """Outcome of a seeding run."""

    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    invalid: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.created) + len(self.skipped) + len(self.invalid)

    def summary(self) -> str:
        """One-line human summary for CLI output."""

        parts = [f"{len(self.created)} created"]
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped (already present)")
        if self.invalid:
            parts.append(f"{len(self.invalid)} invalid")
        return ", ".join(parts)


def existing_test_names(session: Session, project_id: UUID) -> set[str]:
    """Return the set of test names already present in a project."""

    return set(
        session.scalars(
            select(SecurityTest.name).where(SecurityTest.project_id == project_id)
        ).all()
    )


def build_config(case: TestCase) -> dict:
    """Convert a TestCase into the execution engine's config dict.

    ``TestCase.to_config()`` covers prompts, turns, system prompt, grading,
    retries, and timeout. ``category`` is added here because
    ``risk_scoring.extract_test_category()`` reads it to map findings onto the
    OWASP LLM Top 10; without it every report would show ``N/A``.
    """

    plugin = AttackPlugin.from_case(case)
    return {**plugin.execution_config(), "category": plugin.category.value}


def seed_project_tests(
    session: Session,
    project_id: UUID,
    user: User,
    *,
    test_case_dir: Path | None = None,
    categories: set[TestCaseCategory] | None = None,
    skip_existing: bool = True,
    limit: int | None = None,
) -> SeedReport:
    """Load the bundled test case library into a project.

    Idempotent by name: a test whose name already exists in the project is
    skipped, so this is safe to re-run after new YAML files are added. Set
    ``skip_existing=False`` to allow duplicate names.

    ``limit`` caps how many test cases this run considers, counting cases that
    already exist in the project. Re-running with the same ``limit`` is
    therefore a no-op rather than seeding the next N cases each time.
    """

    directory = test_case_dir or DEFAULT_TEST_CASE_DIR
    cases = load_test_cases_from_dir(directory)

    if categories:
        # Reject unknown values rather than silently seeding nothing, which
        # would look like a successful no-op run.
        unknown = {str(c) for c in categories} - {c.value for c in TestCaseCategory}
        if unknown:
            raise ValueError(
                f"unknown test case categories: {', '.join(sorted(unknown))}. "
                f"Valid values: {', '.join(c.value for c in TestCaseCategory)}"
            )
        cases = [case for case in cases if case.category in categories]

    # Authorize before doing anything.
    #
    # create_security_test() authorizes each individual create, but a bulk
    # operation must not rely on that: when every test already exists the loop
    # body never runs, so the per-item check would never fire and an
    # unauthorized caller would be allowed to enumerate the project's tests.
    # Seeding also writes, so it requires mutation rights rather than read.
    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "update")

    existing = existing_test_names(session, project_id) if skip_existing else set()
    report = SeedReport()

    for case in cases:
        # `limit` caps how many tests this run considers, counting ones that
        # already exist. That makes a repeated run with the same --limit a
        # no-op instead of quietly seeding the next N cases each time.
        if limit is not None and report.total >= limit:
            break

        if case.name in existing:
            report.skipped.append(case.name)
            continue

        test = create_security_test(
            session,
            project_id,
            SecurityTestCreate(
                name=case.name,
                description=case.description,
                provider=case.provider,
                required_capabilities=case.required_capabilities,
                config=build_config(case),
            ),
            user,
        )
        # Track names created in this loop so a duplicate within the library
        # itself does not create two rows.
        existing.add(test.name)
        report.created.append(case.name)

    return report


__all__ = [
    "DEFAULT_TEST_CASE_DIR",
    "SeedReport",
    "build_config",
    "existing_test_names",
    "seed_project_tests",
]

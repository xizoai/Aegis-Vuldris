"""Offline demo seeding for Aegis Vuldris.

A brand-new install shows an empty UI until the user has a model endpoint,
credentials, and a project — too much ceremony to see whether the tool is
worth setting up. ``aegis demo`` fixes that: it seeds a synthetic project
from a bundled fixture so every page can be explored with zero provider
credentials.

Honesty rules for demo data, enforced by ``tests/cli/test_demo.py``:

- every seeded row carries a visible ``[DEMO]`` marker (project name,
  description, target, test, finding titles, evidence descriptions);
- the execution is a *recording*: its status and result come from the
  fixture, and its steps are recorded turns, not a live run;
- demo findings are seeded ``open`` and nothing in the demo path can mark
  them ``fixed`` or ``verified`` — those states stay reachable only through
  a human claim plus a passed verification rerun;
- seeding is idempotent per (owner, project name): running it twice never
  duplicates data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.execution_step import ExecutionStep
from app.models.finding import Finding, FindingConfirmation
from app.models.project import Project
from app.models.user import User
from app.schemas import (
    EvidenceCreate,
    ExecutionCreate,
    FindingCreate,
    ProjectCreate,
    SecurityTestCreate,
    TargetCreate,
)
from app.services.assessments import (
    create_evidence,
    create_execution,
    create_finding,
    create_security_test,
)
from app.services.audit import record_audit_event
from app.services.projects import create_project, delete_project
from app.services.targets import create_target

DEMO_MARKER = "[DEMO]"
DEFAULT_DEMO_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "demo" / "demo_run.json"
)
DEFAULT_DEMO_PROJECT_NAME = f"{DEMO_MARKER} Aegis demo"


@dataclass(frozen=True)
class DemoSeedReport:
    """Outcome of a demo seed (or of finding one already seeded)."""

    project_id: UUID
    created: bool
    executions: int
    findings: int
    evidence: int


def load_demo_fixture(fixture_path: Path | None = None) -> dict:
    """Load the bundled demo fixture; every demo row comes from this file."""

    path = fixture_path or DEFAULT_DEMO_FIXTURE
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def find_demo_project(session: Session, user: User, *, project_name: str) -> Project | None:
    """Return this account's demo project, if it was already seeded."""

    return session.scalar(
        select(Project).where(Project.owner_id == user.id, Project.name == project_name)
    )


def _demo_counts(session: Session, project_id: UUID) -> tuple[int, int, int]:
    executions = len(
        list(session.scalars(select(Execution).where(Execution.project_id == project_id)).all())
    )
    findings = len(
        list(
            session.scalars(
                select(Finding)
                .join(Execution, Finding.execution_id == Execution.id)
                .where(Execution.project_id == project_id)
            ).all()
        )
    )
    evidence = len(
        list(
            session.scalars(
                select(Evidence)
                .join(Finding, Evidence.finding_id == Finding.id)
                .join(Execution, Finding.execution_id == Execution.id)
                .where(Execution.project_id == project_id)
            ).all()
        )
    )
    return executions, findings, evidence


def seed_demo_project(
    session: Session,
    user: User,
    *,
    project_name: str = DEFAULT_DEMO_PROJECT_NAME,
    fixture_path: Path | None = None,
) -> DemoSeedReport:
    """Seed (or report) the account's synthetic demo project.

    Idempotent: the demo is identified by (owner, name), so a second call
    reports the existing project instead of duplicating it.
    """

    existing = find_demo_project(session, user, project_name=project_name)
    if existing is not None:
        executions, findings, evidence = _demo_counts(session, existing.id)
        return DemoSeedReport(
            project_id=existing.id,
            created=False,
            executions=executions,
            findings=findings,
            evidence=evidence,
        )

    data = load_demo_fixture(fixture_path)

    project = create_project(
        session,
        ProjectCreate(
            name=project_name,
            description=data["project"]["description"],
        ),
        owner_id=user.id,
    )
    target = create_target(
        session,
        TargetCreate(
            project_id=project.id,
            name=data["target"]["name"],
            description=data["target"]["description"],
            provider=data["target"]["provider"],
            endpoint=data["target"]["endpoint"],
            model=data["target"]["model"],
            capabilities=list(data["target"]["capabilities"]),
            timeout_seconds=30.0,
            authorization_attestation=True,
        ),
        project.id,
        user,
    )
    test = create_security_test(
        session,
        project.id,
        SecurityTestCreate(
            name=data["test"]["name"],
            description=data["test"]["description"],
            provider="openai_compatible",
            required_capabilities=["chat"],
            config={
                "category": data["test"]["category"],
                "prompts": list(data["test"]["prompts"]),
                "grading": dict(data["test"]["grading"]),
            },
        ),
        user,
    )
    execution = create_execution(
        session,
        project.id,
        ExecutionCreate(test_id=test.id, target_id=target.id),
        user,
    )

    # Record the fixture's outcome on the execution row. This is a recording of
    # a past exchange, not a claim that a live run happened here; the [DEMO]
    # markers and the demo.seeded audit entry say exactly that.
    now = datetime.now(UTC)
    execution.status = ExecutionStatus(data["execution"]["status"])
    execution.result = ExecutionResult(data["execution"]["result"])
    execution.started_at = now
    execution.completed_at = now
    for step in data["execution"]["steps"]:
        session.add(
            ExecutionStep(
                execution_id=execution.id,
                turn_number=step["turn_number"],
                request_content=dict(step["request_content"]),
                response_output=step["response_output"],
                status="succeeded",
            )
        )
    session.commit()

    finding_count = 0
    evidence_count = 0
    for finding_data in data["findings"]:
        finding = create_finding(
            session,
            FindingCreate(
                execution_id=execution.id,
                title=finding_data["title"],
                description=finding_data["description"],
                severity=finding_data["severity"],
                details={"synthetic": True, "source": "demo_fixture"},
            ),
            user,
        )
        # The fixture records a run where the attack landed and the execution
        # result is `fail`. Under two-stage grading that pairing only holds if
        # the finding is confirmed — a candidate would make the result
        # `needs_review` — so the recorded verdict is applied explicitly, with
        # a source that says plainly no person or judge decided it.
        finding.confirmation = FindingConfirmation.CONFIRMED
        finding.confirmation_source = "demo-fixture"
        finding.disposition_reason = "Recorded fixture: the response disclosed the system prompt."
        finding.confirmed_at = now
        finding_count += 1
        for evidence_data in finding_data["evidence"]:
            create_evidence(
                session,
                EvidenceCreate(
                    finding_id=finding.id,
                    kind=evidence_data["kind"],
                    description=evidence_data["description"],
                    content=dict(evidence_data["content"]),
                ),
                user,
            )
            evidence_count += 1

    record_audit_event(
        session,
        actor_id=user.id,
        action="demo.seeded",
        resource_type="project",
        resource_id=str(project.id),
        event_metadata={
            "project_id": str(project.id),
            "findings": finding_count,
            "evidence": evidence_count,
            "synthetic": True,
        },
    )

    return DemoSeedReport(
        project_id=project.id,
        created=True,
        executions=1,
        findings=finding_count,
        evidence=evidence_count,
    )


def prune_demo_project(session: Session, user: User, *, project_name: str) -> bool:
    """Delete this account's demo project. Returns whether it existed."""

    existing = find_demo_project(session, user, project_name=project_name)
    if existing is None:
        return False

    deleted = delete_project(session, existing.id, user)
    if deleted:
        record_audit_event(
            session,
            actor_id=user.id,
            action="demo.pruned",
            resource_type="project",
            resource_id=str(existing.id),
            event_metadata={"project_id": str(existing.id), "synthetic": True},
        )
    return deleted

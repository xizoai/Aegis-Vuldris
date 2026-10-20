"""Functional report generation tests: the "changes since baseline" section.

Generating a report with ``baseline_report_id`` embeds the same regression
diff the comparison endpoint and the CLI gate produce, so a reader sees
regressions inside the artifact itself. The baseline must pass the same
project-and-caller authorization as the report being generated.
"""

from uuid import UUID, uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.finding import Finding, FindingSeverity
from app.models.user import User
from app.schemas import (
    ExecutionCreate,
    FindingCreate,
    ReportCreate,
    SecurityTestCreate,
)
from app.services.assessments import (
    create_execution,
    create_finding,
    create_report,
    create_security_test,
)
from app.services.report_generation import generate_report, load_report_snapshot
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"


def _register(email: str | None = None) -> tuple[str, dict[str, str]]:
    email = email or f"report-gen-{uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return email, {"Authorization": f"Bearer {token}"}


def _seed_finding(session, project_id: UUID, user: User, title: str, severity: FindingSeverity):
    test = create_security_test(
        session,
        project_id,
        SecurityTestCreate(
            name=f"Case {uuid4()}",
            provider="openai_compatible",
            config={"category": "prompt_injection"},
        ),
        user,
    )
    execution = create_execution(session, project_id, ExecutionCreate(test_id=test.id), user)
    return create_finding(
        session,
        FindingCreate(execution_id=execution.id, title=title, severity=severity),
        user,
    )


def test_generate_with_baseline_embeds_changes_section() -> None:
    email, auth = _register()
    session = create_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        project_id = UUID(
            client.post(
                "/api/v1/projects", headers=auth, json={"name": f"Baseline {uuid4()}"}
            ).json()["id"]
        )

        # Baseline: generated while the project had one finding.
        _seed_finding(session, project_id, user, "Old issue", FindingSeverity.HIGH)
        baseline = create_report(session, project_id, ReportCreate(title="baseline"), user)
        generate_report(session, baseline)

        # Current: the old finding is resolved, a worse one appears.
        old = session.scalar(select(Finding).where(Finding.title == "Old issue"))
        assert old is not None
        session.delete(old)
        session.commit()
        _seed_finding(session, project_id, user, "New issue", FindingSeverity.CRITICAL)

        current_id = client.post(
            f"/api/v1/projects/{project_id}/assessments/reports",
            headers=auth,
            json={"title": "current", "format": "json"},
        ).json()["id"]

        response = client.post(
            f"/api/v1/projects/{project_id}/assessments/reports/{current_id}/generate",
            headers=auth,
            json={"baseline_report_id": str(baseline.id)},
        )
        assert response.status_code == 200, response.text

        data = load_report_snapshot(session, UUID(current_id), project_id)
        changes = data["changes_since_baseline"]
        assert changes["baseline_report_id"] == str(baseline.id)
        assert changes["new_count"] == 1
        assert changes["new_findings"][0]["title"] == "New issue"
        assert changes["resolved_count"] == 1
        assert changes["resolved_findings"][0]["title"] == "Old issue"
    finally:
        session.close()


def test_generate_rejects_a_baseline_from_another_project() -> None:
    # A caller who learns another tenant's report id must not be able to make
    # the generator read that report's snapshot.
    victim_email, _victim_auth = _register(f"victim-{uuid4()}@example.com")
    attacker_email, attacker_auth = _register(f"attacker-{uuid4()}@example.com")

    session = create_session_factory()()
    try:
        victim = session.scalar(select(User).where(User.email == victim_email))
        attacker = session.scalar(select(User).where(User.email == attacker_email))
        assert victim is not None and attacker is not None

        victim_project = UUID(
            client.post(
                "/api/v1/projects",
                headers={"Authorization": f"Bearer {_token(victim_email)}"},
                json={"name": f"Victim {uuid4()}"},
            ).json()["id"]
        )
        _seed_finding(session, victim_project, victim, "Victim issue", FindingSeverity.HIGH)
        victim_report = create_report(session, victim_project, ReportCreate(title="victim"), victim)
        generate_report(session, victim_report)

        attacker_project = UUID(
            client.post(
                "/api/v1/projects",
                headers=attacker_auth,
                json={"name": f"Attacker {uuid4()}"},
            ).json()["id"]
        )
        attacker_report = create_report(
            session, attacker_project, ReportCreate(title="attacker"), attacker
        )

        response = client.post(
            f"/api/v1/projects/{attacker_project}/assessments/reports/{attacker_report.id}/generate",
            headers=attacker_auth,
            json={"baseline_report_id": str(victim_report.id)},
        )
        assert response.status_code == 404, "cross-tenant baseline must 404, not embed"
    finally:
        session.close()


def _token(email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]

"""Cross-tenant report authorization.

Reports contain the full evidence set for an assessment: every model request
and response. Every report route must therefore verify that the *caller* has
access to the project, not merely that the report's project_id matches the
project_id in the URL path.

A caller who learns a project_id and report_id must not be able to generate,
download, or compare another tenant's reports.
"""

from uuid import UUID, uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.project import Project
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"


def _register(email: str) -> tuple[str, dict[str, str]]:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return email, {"Authorization": f"Bearer {token}"}


def _seed_report() -> tuple[str, str, str]:
    """Create an owner, a project, and a generated report. Return ids."""

    from app.schemas import ReportCreate
    from app.services.assessments import create_report
    from app.services.report_generation import generate_report

    email, auth = _register(f"report-owner-{uuid4()}@example.com")
    session = create_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        project_id = client.post(
            "/api/v1/projects", headers=auth, json={"name": f"Victim {uuid4()}"}
        ).json()["id"]

        report = create_report(
            session,
            UUID(project_id),
            ReportCreate(title="Victim report", format="json"),
            user,
        )
        generate_report(session, report)
        return project_id, str(report.id), email
    finally:
        session.close()


def _cleanup(project_id: str, *emails: str) -> None:
    session = create_session_factory()()
    try:
        project = session.get(Project, UUID(project_id))
        if project is not None:
            session.delete(project)
        for email in emails:
            user = session.scalar(select(User).where(User.email == email))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()


def test_stranger_cannot_generate_report() -> None:
    project_id, report_id, owner_email = _seed_report()
    _, stranger = _register(f"report-stranger-{uuid4()}@example.com")
    try:
        response = client.post(
            f"/api/v1/projects/{project_id}/assessments/reports/{report_id}/generate",
            headers=stranger,
        )
        assert response.status_code in {403, 404}, (
            f"stranger generated another tenant's report: {response.status_code}"
        )
    finally:
        _cleanup(project_id, owner_email)


def test_stranger_cannot_download_report() -> None:
    project_id, report_id, owner_email = _seed_report()
    _, stranger = _register(f"report-dl-{uuid4()}@example.com")
    try:
        response = client.get(
            f"/api/v1/projects/{project_id}/assessments/reports/{report_id}/download",
            headers=stranger,
        )
        assert response.status_code in {403, 404}, (
            f"stranger downloaded another tenant's report: {response.status_code}"
        )
        # No evidence may leak in the body.
        assert "evidence" not in response.text.lower()
    finally:
        _cleanup(project_id, owner_email)


def test_stranger_cannot_compare_reports() -> None:
    project_id, report_id, owner_email = _seed_report()
    _, stranger = _register(f"report-cmp-{uuid4()}@example.com")
    try:
        response = client.get(
            f"/api/v1/projects/{project_id}/assessments/reports/{report_id}/compare/{report_id}",
            headers=stranger,
        )
        assert response.status_code in {403, 404}, (
            f"stranger compared another tenant's reports: {response.status_code}"
        )
    finally:
        _cleanup(project_id, owner_email)


def test_owner_can_still_generate_and_download() -> None:
    """The legitimate path must keep working."""

    project_id, report_id, owner_email = _seed_report()
    _, owner_auth = _register(owner_email)
    try:
        generated = client.post(
            f"/api/v1/projects/{project_id}/assessments/reports/{report_id}/generate",
            headers=owner_auth,
        )
        assert generated.status_code == 200, generated.text

        downloaded = client.get(
            f"/api/v1/projects/{project_id}/assessments/reports/{report_id}/download",
            headers=owner_auth,
        )
        assert downloaded.status_code == 200, downloaded.text
        assert "risk_level" in downloaded.text
    finally:
        _cleanup(project_id, owner_email)


def test_report_id_from_another_project_is_rejected() -> None:
    """A valid report id paired with the wrong project id must not work."""

    project_a, report_a, owner_a = _seed_report()
    project_b, _, owner_b = _seed_report()
    _, owner_b_auth = _register(owner_b)
    try:
        response = client.post(
            f"/api/v1/projects/{project_b}/assessments/reports/{report_a}/generate",
            headers=owner_b_auth,
        )
        assert response.status_code in {403, 404}, response.status_code
    finally:
        _cleanup(project_a, owner_a)
        _cleanup(project_b, owner_b)


def test_unauthenticated_report_routes_rejected() -> None:
    project_id, report_id, owner_email = _seed_report()
    try:
        for method, path in (
            ("post", f"/api/v1/projects/{project_id}/assessments/reports/{report_id}/generate"),
            ("get", f"/api/v1/projects/{project_id}/assessments/reports/{report_id}/download"),
        ):
            response = getattr(client, method)(path)
            assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    finally:
        _cleanup(project_id, owner_email)

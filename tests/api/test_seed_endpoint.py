"""Tests for the security test library seeding endpoint."""

from uuid import UUID, uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.project import Project
from app.models.test import SecurityTest
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)

PASSWORD = "a-very-strong-password-123"


def _cleanup(email: str, project_id: UUID | None = None) -> None:
    session = create_session_factory()()
    try:
        if project_id is not None:
            project = session.get(Project, project_id)
            if project is not None:
                session.delete(project)
        user = session.scalar(select(User).where(User.email == email.lower()))
        if user is not None:
            session.delete(user)
        session.commit()
    finally:
        session.close()


def _setup() -> tuple[str, UUID]:
    email = f"seed-api-{uuid4()}@example.com"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
        ).status_code
        == 201
    )
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]

    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"Seed API {uuid4()}"},
    ).json()["id"]

    return email, UUID(project_id)


def _tests(project_id: UUID, token: str) -> list[dict]:
    response = client.get(
        f"/api/v1/projects/{project_id}/assessments/tests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()


def test_seed_endpoint_creates_the_library() -> None:
    email, project_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    assert _tests(project_id, token) == []

    response = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers=headers,
        json={},
    )

    # A 422 here would mean /tests/seed was captured by /tests/{test_id}.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 224
    assert body["skipped"] == 0
    assert body["total"] == 224

    tests = _tests(project_id, token)
    assert len(tests) == 224
    assert all("grading" in t["config"] for t in tests)
    assert all("category" in t["config"] for t in tests)

    _cleanup(email, project_id)


def test_seed_endpoint_is_idempotent() -> None:
    email, project_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed", headers=headers, json={}
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed", headers=headers, json={}
    )
    assert second.status_code == 200
    body = second.json()
    assert body["created"] == 0
    assert body["skipped"] == 224

    assert len(_tests(project_id, token)) == 224

    _cleanup(email, project_id)


def test_seed_endpoint_filters_by_category() -> None:
    email, project_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers=headers,
        json={"category": ["jailbreak"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 108

    tests = _tests(project_id, token)
    assert len(tests) == 108
    assert all(t["config"]["category"] == "jailbreak" for t in tests)

    _cleanup(email, project_id)


def test_seed_endpoint_rejects_unknown_category() -> None:
    email, project_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]

    response = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": ["not_a_category"]},
    )

    assert response.status_code == 422

    _cleanup(email, project_id)


def test_seed_endpoint_requires_authentication() -> None:
    response = client.post(f"/api/v1/projects/{uuid4()}/assessments/tests/seed", json={})
    assert response.status_code == 401


def test_seed_endpoint_denies_other_users() -> None:
    """Seeding is a write into a project; another tenant must not reach it."""

    email, project_id = _setup()
    owner_token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["access_token"]

    intruder_email = f"seed-intruder-{uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": intruder_email, "password": PASSWORD})
    intruder_token = client.post(
        "/api/v1/auth/login", json={"email": intruder_email, "password": PASSWORD}
    ).json()["access_token"]

    response = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers={"Authorization": f"Bearer {intruder_token}"},
        json={},
    )

    assert response.status_code in {403, 404}, response.status_code

    # The owner's project is untouched.
    assert _tests(project_id, owner_token) == []

    _cleanup(intruder_email)
    _cleanup(email, project_id)


def test_seed_endpoint_denies_stranger_after_project_is_seeded() -> None:
    """Regression: authorization must not depend on there being work to do.

    The bulk seed authorized only inside its per-item create loop. Once every
    test existed the loop never ran, so no check fired and a stranger could
    read the project's test inventory from the summary counts.
    """

    email, project_id = _setup()
    owner_token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["access_token"]

    stranger_email = f"seed-stranger-{uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": stranger_email, "password": PASSWORD})
    stranger_token = client.post(
        "/api/v1/auth/login", json={"email": stranger_email, "password": PASSWORD}
    ).json()["access_token"]
    stranger = {"Authorization": f"Bearer {stranger_token}"}

    # Denied when there is work to do.
    before = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers=stranger,
        json={},
    )
    assert before.status_code in {403, 404}, before.status_code

    # Owner seeds, so the library is fully present.
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/assessments/tests/seed",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={},
        ).status_code
        == 200
    )

    # Must still be denied now that there is nothing left to create.
    after = client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers=stranger,
        json={},
    )
    assert after.status_code in {403, 404}, after.status_code
    # The response must not leak how many tests the project holds.
    assert "skipped" not in after.text

    _cleanup(stranger_email)
    _cleanup(email, project_id)


def test_seed_endpoint_writes_audit_event() -> None:
    email, project_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]

    client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": ["rag_attack"]},
    )

    session = create_session_factory()()
    try:
        from app.models.audit_log import AuditLog

        count = len(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.action == "security_test.created",
                    AuditLog.resource_type == "security_test",
                )
            ).all()
        )
        assert count >= 14
    finally:
        session.close()

    _cleanup(email, project_id)


def test_seeded_tests_are_owned_by_the_project() -> None:
    email, project_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]

    client.post(
        f"/api/v1/projects/{project_id}/assessments/tests/seed",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": ["agent_tool_use"]},
    )

    session = create_session_factory()()
    try:
        rows = session.scalars(
            select(SecurityTest).where(SecurityTest.project_id == project_id)
        ).all()
        assert rows
        assert all(row.project_id == project_id for row in rows)
    finally:
        session.close()

    _cleanup(email, project_id)

"""Credential plaintext must not be retrievable over HTTP.

Target credentials are Fernet-encrypted at rest, and the execution engine
resolves them in-process through ``create_credential_resolver``. That
satisfies every legitimate need for a plaintext value.

The ``POST /targets/{id}/credentials/{cid}/resolve`` endpoint existed
alongside that internal path and returned the decrypted secret to any caller
with read access to the target. It had no caller in the product: the web UI
deliberately never calls it, and the engine does not use HTTP. So it served
one purpose only, which was moving a plaintext secret across a network
boundary into a browser.

These tests pin that the endpoint does not exist and that no response can
carry credential plaintext.
"""

import asyncio
from uuid import uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"


def _setup() -> tuple[str, str, str, str]:
    """Create a user, project, target, and credential. Return ids and email."""

    from app.models.target import TargetProvider
    from app.schemas import CredentialCreate, TargetCreate, UserCreate
    from app.security.secrets import get_secret_store
    from app.services.auth import register_user
    from app.services.credentials import create_target_credential

    email = f"cred-{uuid4()}@example.com"
    session = create_session_factory()()
    try:
        user = register_user(session, UserCreate(email=email, password=PASSWORD))
        token = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        project_id = client.post(
            "/api/v1/projects", headers=headers, json={"name": f"Cred {uuid4()}"}
        ).json()["id"]

        target = client.post(
            "/api/v1/targets",
            headers=headers,
            json=TargetCreate(
                project_id=uuid_of(project_id),
                name="Model",
                provider=TargetProvider.OPENAI_COMPATIBLE,
                endpoint="https://model.example.com/v1",
                model="m",
                authorization_attestation=True,
            ).model_dump(mode="json"),
        ).json()

        credential = create_target_credential(
            session,
            get_secret_store(),
            uuid_of(target["id"]),
            CredentialCreate(credential_type="api_key", value="sk-test-0123"),
            user,
        )
        return project_id, target["id"], str(credential.id), email
    finally:
        session.close()


def uuid_of(value: str):
    from uuid import UUID

    return UUID(value)


def _cleanup(project_id: str, target_id: str, *emails: str) -> None:
    session = create_session_factory()()
    try:
        from app.models.project import Project

        # The project cascade already removes its targets and credentials, so
        # only the projects and users need explicit deletion.
        project = session.get(Project, uuid_of(project_id))
        if project is not None:
            session.delete(project)
        for email in emails:
            user = session.scalar(select(User).where(User.email == email))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()


def test_resolve_route_is_not_registered() -> None:
    """The plaintext-over-HTTP route must not exist at all."""

    paths = app.openapi()["paths"]
    offenders = [path for path in paths if path.endswith("/resolve")]
    assert offenders == [], f"credential resolve route still exposed: {offenders}"


def test_resolve_returns_not_found_for_an_owner() -> None:
    """Even the legitimate owner cannot pull plaintext over HTTP."""

    project_id, target_id, credential_id, email = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    try:
        response = client.post(
            f"/api/v1/projects/{project_id}/assessments/../../targets/{target_id}"
            f"/credentials/{credential_id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in {404, 405}, response.status_code
        assert "sk-test-0123" not in response.text
    finally:
        _cleanup(project_id, target_id, email)


def test_no_credential_endpoint_returns_plaintext() -> None:
    """Credential metadata endpoints must never include the stored value."""

    project_id, target_id, credential_id, email = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        for response in (
            client.get(f"/api/v1/targets/{target_id}/credentials", headers=headers),
            client.get(
                f"/api/v1/targets/{target_id}/credentials/{credential_id}",
                headers=headers,
            ),
        ):
            assert response.status_code == 200, response.status_code
            assert "sk-test-0123" not in response.text
            assert "value" not in response.json()
    finally:
        _cleanup(project_id, target_id, email)


def test_engine_resolves_credentials_internally() -> None:
    """The legitimate path must still work: the engine resolves in-process."""

    from app.adapters.resolver import create_credential_resolver
    from app.security.secrets import get_secret_store

    project_id, target_id, credential_id, email = _setup()
    session = create_session_factory()()

    async def _resolve() -> str | None:
        resolver = create_credential_resolver(session, get_secret_store())
        return await resolver(target_id)

    try:
        # The resolver is async; the engine awaits it in-process.
        value = asyncio.run(_resolve())
        assert value == "sk-test-0123"
    finally:
        session.close()
        _cleanup(project_id, target_id, email)

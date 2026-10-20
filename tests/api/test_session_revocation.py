"""Session revocation.

Access tokens are stateless JWTs, so without an explicit revocation signal a
stolen token stays usable until it expires. These tests pin the behaviour:
after signing out, or signing out everywhere, previously issued tokens must be
rejected while a fresh login works.
"""

from uuid import uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.user import User
from app.security.tokens import (
    create_access_token,
    decode_access_token,
)
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"


def _register() -> str:
    email = f"revoke-{uuid4()}@example.com"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
        ).status_code
        == 201
    )
    return email


def _login(email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _cleanup(*emails: str) -> None:
    session = create_session_factory()()
    try:
        for email in emails:
            user = session.scalar(select(User).where(User.email == email))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()


def test_me_rejects_a_token_after_logout() -> None:
    email = _register()
    token = _login(email)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

        logged_out = client.post("/api/v1/auth/logout", headers=headers)
        assert logged_out.status_code in {200, 204}, logged_out.text

        after = client.get("/api/v1/auth/me", headers=headers)
        assert after.status_code == 401, f"a revoked token still worked: {after.status_code}"
    finally:
        _cleanup(email)


def test_logout_invalidates_every_issued_token() -> None:
    """Signing out everywhere must kill tokens issued earlier, not just the last."""

    email = _register()
    first = _login(email)
    second = _login(email)

    try:
        headers = {"Authorization": f"Bearer {second}"}
        assert client.post("/api/v1/auth/logout-all", headers=headers).status_code in {200, 204}

        for label, token in (("first", first), ("second", second)):
            response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 401, f"{label} token still valid"
    finally:
        _cleanup(email)


def test_a_fresh_login_still_works_after_logout() -> None:
    """Revocation must not lock the account out of its own session."""

    email = _register()
    stale = _login(email)
    headers = {"Authorization": f"Bearer {stale}"}

    try:
        client.post("/api/v1/auth/logout", headers=headers)

        fresh = _login(email)
        assert (
            client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code
            == 200
        )
    finally:
        _cleanup(email)


def test_deactivated_user_cannot_use_an_existing_token() -> None:
    email = _register()
    token = _login(email)
    headers = {"Authorization": f"Bearer {token}"}

    session = create_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        user.is_active = False
        session.commit()

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    finally:
        session.close()
        _cleanup(email)


def test_decoded_token_exposes_its_session_version() -> None:
    """Revocation is decided from the token''s session version."""

    email = _register()
    session = create_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        token, _ = create_access_token(user, session_version=user.session_version or 0)
        claims = decode_access_token(token)
        assert claims.session_version == (user.session_version or 0)
    finally:
        session.close()
        _cleanup(email)


def test_logout_requires_authentication() -> None:
    assert client.post("/api/v1/auth/logout").status_code == 401
    assert client.post("/api/v1/auth/logout-all").status_code == 401

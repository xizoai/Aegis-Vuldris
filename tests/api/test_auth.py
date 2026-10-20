"""Authentication API tests for Aegis Vuldris."""

from uuid import uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)


def _cleanup_user(email: str) -> None:
    session = create_session_factory()()

    try:
        user = session.scalar(select(User).where(User.email == email.lower()))

        if user is not None:
            session.delete(user)
            session.commit()
    finally:
        session.close()


def test_register_endpoint_creates_user() -> None:
    """Registering via the API creates a user and never returns the password."""

    email = f"api-register-{uuid4()}@example.com"

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "a-very-strong-password-123"},
        )

        assert response.status_code == 201

        body = response.json()

        assert body["email"] == email.lower()
        assert "password" not in body
        assert "hashed_password" not in body
    finally:
        _cleanup_user(email)


def test_register_duplicate_email_returns_409() -> None:
    """Registering an already-used email returns EMAIL_ALREADY_REGISTERED."""

    email = f"api-dup-{uuid4()}@example.com"

    try:
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "a-very-strong-password-123"},
        )

        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "another-strong-password"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    finally:
        _cleanup_user(email)


def test_login_success_returns_token() -> None:
    """A registered user can log in and receive a bearer access token."""

    email = f"api-login-{uuid4()}@example.com"
    password = "a-very-strong-password-123"

    try:
        client.post("/api/v1/auth/register", json={"email": email, "password": password})

        response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )

        assert response.status_code == 200

        body = response.json()

        assert body["token_type"] == "bearer"
        assert isinstance(body["access_token"], str)
        assert len(body["access_token"]) > 0
        assert body["expires_in"] > 0
    finally:
        _cleanup_user(email)


def test_login_wrong_password_returns_401() -> None:
    """Logging in with an incorrect password returns INVALID_CREDENTIALS."""

    email = f"api-badlogin-{uuid4()}@example.com"
    password = "a-very-strong-password-123"

    try:
        client.post("/api/v1/auth/register", json={"email": email, "password": password})

        response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "totally-wrong-password"},
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    finally:
        _cleanup_user(email)


def test_me_requires_authentication() -> None:
    """Requesting the current user without a token returns AUTHENTICATION_REQUIRED."""

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_me_rejects_invalid_token() -> None:
    """Requesting the current user with a malformed token is rejected."""

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_login_rate_limit_returns_429_after_threshold() -> None:
    """Exceeding the login endpoint's rate limit returns RATE_LIMIT_EXCEEDED."""

    email = f"api-ratelimit-login-{uuid4()}@example.com"
    password = "a-very-strong-password-123"

    try:
        client.post("/api/v1/auth/register", json={"email": email, "password": password})

        last_response = None
        for _ in range(11):
            last_response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "totally-wrong-password"},
            )

        assert last_response is not None
        assert last_response.status_code == 429
        assert last_response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in last_response.headers
    finally:
        _cleanup_user(email)


def test_register_rate_limit_returns_429_after_threshold() -> None:
    """Exceeding the register endpoint's rate limit returns RATE_LIMIT_EXCEEDED."""

    emails = [f"api-ratelimit-register-{uuid4()}@example.com" for _ in range(6)]

    try:
        last_response = None
        for email in emails:
            last_response = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "a-very-strong-password-123"},
            )

        assert last_response is not None
        assert last_response.status_code == 429
        assert last_response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    finally:
        for email in emails:
            _cleanup_user(email)


def test_me_returns_current_user_with_valid_token() -> None:
    """A valid access token resolves to the authenticated user's own profile."""

    email = f"api-me-{uuid4()}@example.com"
    password = "a-very-strong-password-123"

    try:
        client.post("/api/v1/auth/register", json={"email": email, "password": password})

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )

        token = login_response.json()["access_token"]

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

        body = response.json()

        assert body["email"] == email.lower()
        assert "password" not in body
        assert "hashed_password" not in body
    finally:
        _cleanup_user(email)

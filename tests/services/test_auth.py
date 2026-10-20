"""Authentication service tests for Aegis Vuldris."""

from uuid import UUID, uuid4

from app.api.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.db.session import create_session_factory
from app.models.user import User
from app.schemas import UserCreate
from app.security.passwords import verify_password
from app.services.auth import authenticate_user, register_user
from sqlalchemy.orm import Session


def create_test_session() -> Session:
    """Create a real PostgreSQL session for service integration tests."""

    return create_session_factory()()


def _cleanup_user(session: Session, user_id: UUID) -> None:
    remaining = session.get(User, user_id)

    if remaining is not None:
        session.delete(remaining)
        session.commit()


def test_register_user_hashes_password() -> None:
    """Registering a user stores an Argon2 hash, never the plaintext password."""

    session = create_test_session()

    user = None

    try:
        payload = UserCreate(
            email=f"register-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        )

        user = register_user(session, payload)

        assert user.id is not None
        assert user.email == payload.email.lower()
        assert user.hashed_password != payload.password
        assert verify_password(payload.password, user.hashed_password) is True
    finally:
        if user is not None and session.get(User, user.id) is not None:
            _cleanup_user(session, user.id)

        session.close()


def test_register_user_normalizes_email_case() -> None:
    """Email addresses are normalized to lowercase on registration."""

    session = create_test_session()

    user = None

    try:
        raw_email = f"MixedCase-{uuid4()}@Example.com"

        payload = UserCreate(email=raw_email, password="a-very-strong-password-123")

        user = register_user(session, payload)

        assert user.email == raw_email.lower()
    finally:
        if user is not None and session.get(User, user.id) is not None:
            _cleanup_user(session, user.id)

        session.close()


def test_register_user_duplicate_email_raises() -> None:
    """Registering an already-used email raises EmailAlreadyRegisteredError."""

    session = create_test_session()

    user = None

    try:
        email = f"duplicate-{uuid4()}@example.com"

        payload = UserCreate(email=email, password="a-very-strong-password-123")

        user = register_user(session, payload)

        try:
            register_user(session, UserCreate(email=email, password="another-strong-password"))
            raise AssertionError("Expected EmailAlreadyRegisteredError")
        except EmailAlreadyRegisteredError:
            pass
    finally:
        if user is not None and session.get(User, user.id) is not None:
            _cleanup_user(session, user.id)

        session.close()


def test_authenticate_user_success() -> None:
    """A user can authenticate with the correct email and password."""

    session = create_test_session()

    user = None

    try:
        password = "a-very-strong-password-123"
        payload = UserCreate(email=f"auth-{uuid4()}@example.com", password=password)

        user = register_user(session, payload)

        authenticated = authenticate_user(session, payload.email, password)

        assert authenticated.id == user.id
    finally:
        if user is not None and session.get(User, user.id) is not None:
            _cleanup_user(session, user.id)

        session.close()


def test_authenticate_user_wrong_password_raises() -> None:
    """Authenticating with an incorrect password raises InvalidCredentialsError."""

    session = create_test_session()

    user = None

    try:
        payload = UserCreate(
            email=f"wrongpass-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        )

        user = register_user(session, payload)

        try:
            authenticate_user(session, payload.email, "totally-wrong-password")
            raise AssertionError("Expected InvalidCredentialsError")
        except InvalidCredentialsError:
            pass
    finally:
        if user is not None and session.get(User, user.id) is not None:
            _cleanup_user(session, user.id)

        session.close()


def test_authenticate_user_unknown_email_raises() -> None:
    """Authenticating with an unregistered email raises InvalidCredentialsError."""

    session = create_test_session()

    try:
        try:
            authenticate_user(
                session,
                f"nobody-{uuid4()}@example.com",
                "irrelevant-password",
            )
            raise AssertionError("Expected InvalidCredentialsError")
        except InvalidCredentialsError:
            pass
    finally:
        session.close()


def test_authenticate_user_inactive_account_raises() -> None:
    """Authenticating a deactivated account raises InvalidCredentialsError."""

    session = create_test_session()

    user = None

    try:
        password = "a-very-strong-password-123"
        payload = UserCreate(email=f"inactive-{uuid4()}@example.com", password=password)

        user = register_user(session, payload)

        user.is_active = False
        session.commit()

        try:
            authenticate_user(session, payload.email, password)
            raise AssertionError("Expected InvalidCredentialsError")
        except InvalidCredentialsError:
            pass
    finally:
        if user is not None and session.get(User, user.id) is not None:
            _cleanup_user(session, user.id)

        session.close()

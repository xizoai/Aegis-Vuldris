"""Authentication service operations for Aegis Vuldris."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.models.user import User
from app.schemas import UserCreate
from app.security.passwords import hash_password, verify_password


def register_user(
    session: Session,
    payload: UserCreate,
) -> User:
    """Register a new user account.

    Raises EmailAlreadyRegisteredError if the email is already in use.
    """

    normalized_email = payload.email.strip().lower()

    existing = session.scalar(select(User).where(User.email == normalized_email))

    if existing is not None:
        raise EmailAlreadyRegisteredError()

    user = User(
        email=normalized_email,
        hashed_password=hash_password(payload.password),
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


def authenticate_user(
    session: Session,
    email: str,
    password: str,
) -> User:
    """Authenticate a user by email and password.

    Raises InvalidCredentialsError for any unknown email, incorrect
    password, or deactivated account. Deliberately uses the same error for
    every failure mode so as not to reveal whether an email is registered.

    Brute-force protection is provided by the IP-based sliding-window rate
    limiter on ``POST /auth/login`` (10 requests / 60 seconds per client IP).
    Per-account lockout is intentionally NOT implemented: it creates a
    trivial denial-of-service vector where an attacker can lock legitimate
    users out of their accounts. The rate limiter covers brute-force volume
    and is upgraded to a shared-state (Redis-backed) implementation during
    Phase 6 deployment.
    """

    normalized_email = email.strip().lower()

    user = session.scalar(select(User).where(User.email == normalized_email))

    if user is None or not user.is_active:
        raise InvalidCredentialsError()

    if not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError()

    return user

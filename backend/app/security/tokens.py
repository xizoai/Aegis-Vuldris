"""JWT access token utilities for Aegis Vuldris.

Uses PyJWT exclusively. Never implement token signing or verification
manually.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import get_settings
from app.models.user import User


@dataclass(frozen=True)
class AccessTokenClaims:
    """The claims Aegis Vuldris needs from an access token."""

    user_id: UUID
    session_version: int


class InvalidTokenError(Exception):
    """Raised when a JWT access token is missing, invalid, or expired."""


def revoke_sessions(user: User) -> int:
    """Invalidate every token minted before now and return the new version.

    Counting rather than comparing timestamps: JWT ``iat`` only has second
    granularity, so a timestamp cut-off either lets a same-second sign-out fail
    silently or wrongly rejects a same-second sign-in. A counter is exact.
    """

    user.session_version = (user.session_version or 0) + 1
    return user.session_version


def is_token_revoked(token_version: int, current_version: int | None) -> bool:
    """Return whether a token minted under ``token_version`` has been revoked."""

    if current_version is None:
        return False
    return token_version < current_version


def create_access_token(user: User | UUID, *, session_version: int = 0) -> tuple[str, int]:
    """Create a signed JWT access token for the given user ID.

    Returns a tuple of (encoded token, lifetime in seconds). Raises
    RuntimeError if SECRET_KEY has not been configured, since signing a
    token with an empty key would be insecure.
    """
    user_id = user.id if isinstance(user, User) else user

    settings = get_settings()

    if not settings.secret_key.strip():
        raise RuntimeError("SECRET_KEY must be configured to issue access tokens.")

    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + expires_delta,
        # Carried so revocation can be decided without server-side token state.
        "sv": int(session_version),
    }

    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> "AccessTokenClaims":
    """Decode and validate a JWT access token.

    Returns the subject user ID and the token's issue time. The issue time is
    required for session revocation: a stateless token cannot be withdrawn, so
    it is compared against the user's revocation cut-off instead.
    """

    settings = get_settings()

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Invalid or expired access token.") from exc

    subject = payload.get("sub")

    if not subject:
        raise InvalidTokenError("Access token is missing a subject.")

    try:
        user_id = UUID(str(subject))
    except ValueError as exc:
        raise InvalidTokenError("Access token subject is not a valid user ID.") from exc

    session_version = payload.get("sv")
    if session_version is None:
        # A token without a session version cannot be checked for revocation.
        raise InvalidTokenError("Access token is missing a session version.")

    return AccessTokenClaims(
        user_id=user_id,
        session_version=int(session_version),
    )

"""Authentication dependencies for Aegis Vuldris API routes."""

import hmac
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.errors import AuthenticationRequiredError, ServiceAuthenticationError
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.user import User
from app.security.tokens import InvalidTokenError, decode_access_token, is_token_revoked

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
) -> User:
    """Resolve the current authenticated user from a bearer access token.

    Raises AuthenticationRequiredError when no token is supplied, the token
    is invalid or expired, or the referenced user no longer exists or has
    been deactivated.
    """

    if credentials is None:
        raise AuthenticationRequiredError()

    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise AuthenticationRequiredError() from exc

    user = session.get(User, claims.user_id)

    if user is None or not user.is_active:
        raise AuthenticationRequiredError()

    # A stateless token cannot be withdrawn, so it is refused if it was issued
    # before the user's revocation cut-off. This is what makes sign-out
    # immediate rather than effective only at expiry.
    if is_token_revoked(claims.session_version, user.session_version):
        raise AuthenticationRequiredError()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_runner_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> None:
    """Authorize an internal request from the external scan runner.

    The runner holds only this shared token: no database credentials and no
    target credentials. Comparison uses ``hmac.compare_digest`` so the expected
    value cannot be recovered by timing. An unset token disables the internal
    endpoints rather than leaving them open.
    """

    expected = get_settings().runner_service_token.strip()

    if not expected:
        raise ServiceAuthenticationError("Runner access is not configured.")

    if credentials is None:
        raise ServiceAuthenticationError()

    if not hmac.compare_digest(
        credentials.credentials.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise ServiceAuthenticationError()


__all__ = ["CurrentUser", "get_current_user", "require_runner_token"]

"""Authentication API routes for Aegis Vuldris."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserResponse
from app.security.dependencies import CurrentUser
from app.security.rate_limit import enforce_login_rate_limit, enforce_register_rate_limit
from app.security.tokens import create_access_token, revoke_sessions
from app.services.audit import record_audit_event
from app.services.auth import authenticate_user, register_user

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
async def register_endpoint(
    payload: UserCreate,
    session: DatabaseSession,
) -> UserResponse:
    """Register a new user account."""

    user = register_user(session, payload)

    record_audit_event(
        session,
        actor_id=user.id,
        action="user.registered",
        resource_type="user",
        resource_id=str(user.id),
    )

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login_endpoint(
    payload: LoginRequest,
    session: DatabaseSession,
) -> TokenResponse:
    """Authenticate a user and issue an access token."""

    user = authenticate_user(session, payload.email, payload.password)

    access_token, expires_in = create_access_token(user, session_version=user.session_version or 0)

    record_audit_event(
        session,
        actor_id=user.id,
        action="user.login",
        resource_type="user",
        resource_id=str(user.id),
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me_endpoint(
    current_user: CurrentUser,
) -> UserResponse:
    """Return the currently authenticated user."""

    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout_endpoint(
    current_user: CurrentUser,
    session: DatabaseSession,
) -> None:
    """Invalidate every access token previously issued to this account.

    Access tokens are stateless, so signing out advances a revocation cut-off
    on the user. Tokens issued before it are refused immediately rather than
    remaining usable until they expire. This signs the account out everywhere,
    because there is no per-token state to revoke a single session.
    """

    revoke_sessions(current_user)
    session.commit()

    record_audit_event(
        session,
        actor_id=current_user.id,
        action="user.logout",
        resource_type="user",
        resource_id=str(current_user.id),
    )


# `logout-all` is retained as an explicit alias so callers can state the
# account-wide intent rather than relying on knowing that logout is broad.
@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout_all_endpoint(
    current_user: CurrentUser,
    session: DatabaseSession,
) -> None:
    """Invalidate every access token previously issued to this account."""

    await logout_endpoint(current_user, session)

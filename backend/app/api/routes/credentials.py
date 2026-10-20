"""Target credential API routes for Aegis Vuldris."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.errors import CredentialNotFoundError
from app.db.session import get_db_session
from app.models.target import Target
from app.schemas import CredentialCreate, CredentialResponse
from app.security.dependencies import CurrentUser
from app.security.secrets import SecretStore, get_secret_store
from app.services.audit import record_audit_event
from app.services.credentials import (
    create_target_credential,
    delete_target_credential,
    get_credential,
    list_target_credentials,
    revoke_target_credential,
    rotate_target_credential,
)
from app.services.targets import ensure_target_access

router = APIRouter(
    prefix="/targets/{target_id}/credentials",
    tags=["target-credentials"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]
SecretStoreDep = Annotated[SecretStore, Depends(get_secret_store)]


def _credential_response(credential) -> CredentialResponse:
    return CredentialResponse.model_validate(credential)


def _require_target_access(
    session: Session,
    current_user: CurrentUser,
    target_id: UUID,
    operation: str,
) -> Target:
    target = session.get(Target, target_id)
    if target is None:
        raise CredentialNotFoundError()
    ensure_target_access(session, current_user, target, operation)
    return target


@router.post(
    "",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential_endpoint(
    target_id: UUID,
    payload: CredentialCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
    secret_store: SecretStoreDep,
) -> CredentialResponse:
    """Create an encrypted credential for an authorized target."""

    credential = create_target_credential(
        session,
        secret_store,
        target_id,
        payload,
        current_user,
    )
    return _credential_response(credential)


@router.get(
    "",
    response_model=list[CredentialResponse],
)
async def list_credentials_endpoint(
    target_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[CredentialResponse]:
    """Return the credential metadata for an authorized target."""

    _require_target_access(session, current_user, target_id, "read")
    credentials = list_target_credentials(session, target_id, current_user)
    return [_credential_response(credential) for credential in credentials]


@router.get(
    "/{credential_id}",
    response_model=CredentialResponse,
)
async def get_credential_endpoint(
    target_id: UUID,
    credential_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> CredentialResponse:
    """Return a single authorized credential's metadata."""

    credential = get_credential(session, credential_id)
    if credential.target_id != target_id:
        raise CredentialNotFoundError()
    _require_target_access(session, current_user, target_id, "read")
    return _credential_response(credential)


@router.post(
    "/{credential_id}/revoke",
    response_model=CredentialResponse,
)
async def revoke_credential_endpoint(
    target_id: UUID,
    credential_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> CredentialResponse:
    """Revoke an authorized credential."""

    credential = revoke_target_credential(session, credential_id, current_user)
    if credential.target_id != target_id:
        raise CredentialNotFoundError()
    return _credential_response(credential)


@router.post(
    "/{credential_id}/rotate",
    response_model=CredentialResponse,
)
async def rotate_credential_endpoint(
    target_id: UUID,
    credential_id: UUID,
    payload: CredentialCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
    secret_store: SecretStoreDep,
) -> CredentialResponse:
    """Rotate an authorized credential with a new value."""

    credential = rotate_target_credential(
        session,
        secret_store,
        credential_id,
        payload.value,
        current_user,
    )
    if credential.target_id != target_id:
        raise CredentialNotFoundError()
    return _credential_response(credential)


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_credential_endpoint(
    target_id: UUID,
    credential_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> None:
    """Delete an authorized credential."""

    credential = get_credential(session, credential_id)
    if credential.target_id != target_id:
        raise CredentialNotFoundError()
    if not delete_target_credential(session, credential_id, current_user):
        raise CredentialNotFoundError()

    record_audit_event(
        session,
        actor_id=current_user.id,
        action="target_credential.deleted",
        resource_type="target_credential",
        resource_id=str(credential_id),
    )

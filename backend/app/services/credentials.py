"""Target credential service operations for Aegis Vuldris.

Credentials are encrypted at rest and scoped to a single target. A target may
retain multiple historic versions, but only one active (non-revoked) credential
of a given type is permitted at any time.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import (
    CredentialNotFoundError,
    TargetNotFoundError,
)
from app.models.credential import TargetCredential
from app.models.target import Target
from app.models.user import User
from app.schemas import CredentialCreate
from app.security.secrets import SecretStore
from app.services.audit import record_audit_event
from app.services.targets import ensure_target_access


def get_credential(
    session: Session,
    credential_id: UUID,
) -> TargetCredential:
    """Return a credential by ID or raise CredentialNotFoundError."""

    credential = session.get(TargetCredential, credential_id)
    if credential is None:
        raise CredentialNotFoundError()
    return credential


def get_active_credential(
    session: Session,
    target_id: UUID,
    *,
    credential_type: str = "api_key",
) -> TargetCredential | None:
    """Return the active (non-revoked) credential for a target and type."""

    return session.scalar(
        select(TargetCredential)
        .where(
            TargetCredential.target_id == target_id,
            TargetCredential.credential_type == credential_type,
            TargetCredential.revoked.is_(False),
        )
        .order_by(TargetCredential.version.desc())
        .limit(1)
    )


def resolve_credential_value(
    session: Session,
    store: SecretStore,
    target_id: UUID,
    *,
    credential_type: str = "api_key",
) -> str | None:
    """Resolve and decrypt the active credential value for a target."""

    credential = get_active_credential(session, target_id, credential_type=credential_type)
    if credential is None:
        return None
    return store.decrypt(credential.encrypted_value)


def _latest_version(session: Session, target_id: UUID, credential_type: str) -> int:
    latest = session.scalar(
        select(TargetCredential.version)
        .where(
            TargetCredential.target_id == target_id,
            TargetCredential.credential_type == credential_type,
        )
        .order_by(TargetCredential.version.desc())
        .limit(1)
    )
    return int(latest) if latest is not None else 0


def create_target_credential(
    session: Session,
    store: SecretStore,
    target_id: UUID,
    payload: CredentialCreate,
    user: User,
) -> TargetCredential:
    """Create and persist an encrypted credential for an authorized target."""

    target = session.get(Target, target_id)
    if target is None:
        raise TargetNotFoundError()
    ensure_target_access(session, user, target, "manage_credentials")

    previous = get_active_credential(session, target_id, credential_type=payload.credential_type)
    if previous is not None:
        previous.revoked = True
        session.add(previous)

    version = _latest_version(session, target_id, payload.credential_type) + 1
    credential = TargetCredential(
        target_id=target_id,
        credential_type=payload.credential_type,
        encrypted_value=store.encrypt(payload.value),
        version=version,
        revoked=False,
    )
    session.add(credential)
    session.commit()
    session.refresh(credential)

    record_audit_event(
        session,
        actor_id=user.id,
        action="credential.created",
        resource_type="target_credential",
        resource_id=str(credential.id),
        event_metadata={
            "target_id": str(target_id),
            "credential_type": payload.credential_type,
            "version": version,
            "rotated_from": str(previous.id) if previous is not None else None,
        },
    )

    return credential


def revoke_target_credential(
    session: Session,
    credential_id: UUID,
    user: User,
    *,
    reason: str | None = None,
) -> TargetCredential:
    """Revoke an authorized credential."""

    credential = get_credential(session, credential_id)
    target = session.get(Target, credential.target_id)
    if target is None:
        raise TargetNotFoundError()
    ensure_target_access(session, user, target, "manage_credentials")

    if not credential.revoked:
        credential.revoked = True
        session.add(credential)
        session.commit()
        session.refresh(credential)

    record_audit_event(
        session,
        actor_id=user.id,
        action="credential.revoked",
        resource_type="target_credential",
        resource_id=str(credential.id),
        event_metadata={"target_id": str(credential.target_id), "reason": reason},
    )

    return credential


def rotate_target_credential(
    session: Session,
    store: SecretStore,
    credential_id: UUID,
    value: str,
    user: User,
) -> TargetCredential:
    """Rotate a credential by revoking the current value and creating a successor."""

    revoked = revoke_target_credential(session, credential_id, user, reason="rotation")
    return create_target_credential(
        session,
        store,
        revoked.target_id,
        CredentialCreate(
            credential_type=revoked.credential_type,
            value=value,
        ),
        user,
    )


def delete_target_credential(
    session: Session,
    credential_id: UUID,
    user: User,
) -> bool:
    """Delete an authorized credential, returning whether one was deleted."""

    credential = get_credential(session, credential_id)
    target = session.get(Target, credential.target_id)
    if target is None:
        raise TargetNotFoundError()
    ensure_target_access(session, user, target, "manage_credentials")

    session.delete(credential)
    session.commit()

    record_audit_event(
        session,
        actor_id=user.id,
        action="credential.deleted",
        resource_type="target_credential",
        resource_id=str(credential_id),
        event_metadata={"target_id": str(credential.target_id)},
    )

    return True


def list_target_credentials(
    session: Session,
    target_id: UUID,
    user: User,
) -> list[TargetCredential]:
    """Return the credentials for a target visible to an authorized user."""

    target = session.get(Target, target_id)
    if target is None:
        raise TargetNotFoundError()
    ensure_target_access(session, user, target, "read")

    return list(
        session.scalars(
            select(TargetCredential)
            .where(TargetCredential.target_id == target_id)
            .order_by(TargetCredential.version.desc(), TargetCredential.created_at)
        ).all()
    )


def ensure_target_access_or_raise(
    session: Session,
    user: User,
    target_id: UUID,
    operation: str,
) -> Target:
    """Authorize access to a target for credential operations."""

    target = session.get(Target, target_id)
    if target is None:
        raise TargetNotFoundError()
    ensure_target_access(session, user, target, operation)
    return target

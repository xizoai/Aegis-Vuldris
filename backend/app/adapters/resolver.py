"""Adapter credential resolution backed by the target credential store."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.security.secrets import SecretStore
from app.services.credentials import resolve_credential_value


def create_credential_resolver(
    session: Session,
    store: SecretStore,
) -> Callable[[str], Awaitable[str | None]]:
    """Return an awaitable callable resolving a target ID to its credential.

    The returned resolver is intended for use as a ``CredentialResolver`` by
    model adapters. Credential resolution occurs only after authorization and
    remains scoped to the supplied target identifier.
    """

    async def resolve(target_id: str) -> str | None:
        return resolve_credential_value(session, store, UUID(target_id))

    return resolve

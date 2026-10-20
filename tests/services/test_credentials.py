"""Target credential service tests for Aegis Vuldris."""

from uuid import uuid4

import pytest
from app.api.errors import CredentialNotFoundError
from app.db.session import create_session_factory
from app.models.credential import TargetCredential
from app.models.project import Project
from app.models.target import Target, TargetProvider, TargetStatus
from app.models.user import User
from app.schemas import CredentialCreate, ProjectCreate, TargetCreate, UserCreate
from app.security.secrets import SecretStore
from app.services.auth import register_user
from app.services.credentials import (
    create_target_credential,
    delete_target_credential,
    get_active_credential,
    get_credential,
    list_target_credentials,
    resolve_credential_value,
    revoke_target_credential,
    rotate_target_credential,
)
from app.services.projects import create_project
from app.services.targets import create_target
from sqlalchemy import select
from sqlalchemy.orm import Session

_TEST_SECRET_KEY = "test-encryption-key-do-not-use-in-production"


def _store() -> SecretStore:
    return SecretStore(_TEST_SECRET_KEY)


def _create_session() -> Session:
    return create_session_factory()()


def _register_user(session: Session, suffix: str = "credential-user") -> User:
    return register_user(
        session,
        UserCreate(
            email=f"{suffix}-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )


def _create_target(session: Session, user: User) -> Target:
    project = create_project(
        session,
        ProjectCreate(name=f"Credential Project {uuid4()}"),
        owner_id=user.id,
    )
    return create_target(
        session,
        TargetCreate(
            project_id=project.id,
            name=f"Credential Target {uuid4()}",
            description="credential service test",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="test-model",
            capabilities=["chat"],
            timeout_seconds=45.0,
            rate_limit_per_minute=120,
            status=TargetStatus.ACTIVE,
            authorization_attestation=True,
        ),
        project_id=project.id,
        user=user,
    )


def _payload(value: str = "test-api-key") -> CredentialCreate:
    return CredentialCreate(credential_type="api_key", value=value)


def _cleanup(session: Session, target: Target, project: Project | None) -> None:
    session.delete(target)
    if project is not None:
        session.delete(project)
    session.commit()
    session.close()


def test_create_credential_encrypts_value_and_revokes_previous() -> None:
    session = _create_session()
    user = _register_user(session)
    target = _create_target(session, user)
    project = session.get(Project, target.project_id)
    store = _store()

    try:
        first = create_target_credential(session, store, target.id, _payload(), user)
        assert first.encrypted_value != "test-api-key"
        assert resolve_credential_value(session, store, target.id) == "test-api-key"

        second = create_target_credential(
            session, store, target.id, _payload(value="rotated-api-key"), user
        )
        active = get_active_credential(session, target.id)
        assert active is not None
        assert active.id == second.id
        assert resolve_credential_value(session, store, target.id) == "rotated-api-key"
        previous = session.get(TargetCredential, first.id)
        assert previous is not None
        assert previous.revoked is True
    finally:
        _cleanup(session, target, project)


def test_revoked_credential_is_not_resolved() -> None:
    session = _create_session()
    user = _register_user(session, suffix="revoke-user")
    target = _create_target(session, user)
    project = session.get(Project, target.project_id)
    store = _store()

    try:
        credential = create_target_credential(session, store, target.id, _payload(), user)
        revoke_target_credential(session, credential.id, user)
        assert resolve_credential_value(session, store, target.id) is None
        assert get_active_credential(session, target.id) is None
    finally:
        _cleanup(session, target, project)


def test_rotate_creates_new_version_and_revokes_previous() -> None:
    session = _create_session()
    user = _register_user(session, suffix="rotate-user")
    target = _create_target(session, user)
    project = session.get(Project, target.project_id)
    store = _store()

    try:
        credential = create_target_credential(session, store, target.id, _payload(), user)
        rotated = rotate_target_credential(session, store, credential.id, "new-key", user)
        assert rotated.version == credential.version + 1
        assert resolve_credential_value(session, store, target.id) == "new-key"
        original = session.get(TargetCredential, credential.id)
        assert original is not None
        assert original.revoked is True
    finally:
        _cleanup(session, target, project)


def test_delete_removes_credential() -> None:
    session = _create_session()
    user = _register_user(session, suffix="delete-user")
    target = _create_target(session, user)
    project = session.get(Project, target.project_id)
    store = _store()

    try:
        credential = create_target_credential(session, store, target.id, _payload(), user)
        assert delete_target_credential(session, credential.id, user) is True
        with pytest.raises(CredentialNotFoundError):
            get_credential(session, credential.id)
    finally:
        _cleanup(session, target, project)


def test_list_returns_all_versions() -> None:
    session = _create_session()
    user = _register_user(session, suffix="list-user")
    target = _create_target(session, user)
    project = session.get(Project, target.project_id)
    store = _store()

    try:
        create_target_credential(session, store, target.id, _payload(), user)
        create_target_credential(session, store, target.id, _payload(value="second"), user)
        credentials = list_target_credentials(session, target.id, user)
        assert {c.version for c in credentials} == {1, 2}
    finally:
        _cleanup(session, target, project)


def test_resolved_secret_is_not_persisted_in_plaintext() -> None:
    session = _create_session()
    user = _register_user(session, suffix="plaintext-user")
    target = _create_target(session, user)
    project = session.get(Project, target.project_id)
    store = _store()

    try:
        credential = create_target_credential(session, store, target.id, _payload(), user)
        leaked = session.scalar(
            select(TargetCredential.encrypted_value).where(TargetCredential.id == credential.id)
        )
        assert leaked is not None
        assert "test-api-key" not in leaked
    finally:
        _cleanup(session, target, project)

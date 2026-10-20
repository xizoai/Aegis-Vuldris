"""Cross-tenant resource binding for executions.

An execution is created inside a project. Its ``test_id`` and ``target_id``
must both belong to that same project. Otherwise a tenant could create an
execution in their own project that points at another tenant's target, and
the engine would resolve that target's stored credentials and send
attacker-chosen prompts to it.
"""

from uuid import uuid4

import pytest
from app.api.errors import AssessmentNotFoundError
from app.db.session import create_session_factory
from app.models.target import TargetProvider
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas import (
    ExecutionCreate,
    ProjectCreate,
    SecurityTestCreate,
    TargetCreate,
    UserCreate,
)
from app.services.assessments import create_execution, create_security_test
from app.services.auth import register_user
from app.services.projects import create_project
from app.services.targets import create_target
from sqlalchemy.orm import Session

PASSWORD = "a-very-strong-password"


def _session() -> Session:
    return create_session_factory()()


def _user(session: Session) -> User:
    return register_user(
        session, UserCreate(email=f"binding-{uuid4()}@example.com", password=PASSWORD)
    )


def _project(session: Session, owner: User):
    return create_project(session, ProjectCreate(name=f"Binding {uuid4()}"), owner_id=owner.id)


def _test(session: Session, project, owner: User) -> SecurityTest:
    return create_security_test(
        session,
        project.id,
        SecurityTestCreate(
            name="Case",
            provider="openai_compatible",
            config={"prompts": [{"role": "user", "content": "hi"}]},
        ),
        owner,
    )


def _target(session: Session, project, owner: User, name: str):
    return create_target(
        session,
        TargetCreate(
            project_id=project.id,
            name=name,
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="test-model",
            authorization_attestation=True,
        ),
        project_id=project.id,
        user=owner,
    )


def test_execution_rejects_target_from_another_project() -> None:
    """The core cross-tenant check: target must be inside the same project."""

    session = _session()
    victim = _user(session)
    attacker = _user(session)
    victim_project = _project(session, victim)
    attacker_project = _project(session, attacker)
    attacker_test = _test(session, attacker_project, attacker)
    victim_target = _target(session, victim_project, victim, "Victim target")

    try:
        with pytest.raises(AssessmentNotFoundError):
            create_execution(
                session,
                attacker_project.id,
                ExecutionCreate(
                    test_id=attacker_test.id,
                    target_id=victim_target.id,
                ),
                attacker,
            )
    finally:
        for project in (victim_project, attacker_project):
            session.delete(project)
        session.commit()
        session.close()


def test_execution_rejects_unknown_target() -> None:
    session = _session()
    owner = _user(session)
    project = _project(session, owner)
    test = _test(session, project, owner)

    try:
        with pytest.raises(AssessmentNotFoundError):
            create_execution(
                session,
                project.id,
                ExecutionCreate(test_id=test.id, target_id=uuid4()),
                owner,
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_execution_accepts_same_project_target() -> None:
    """The legitimate path must keep working."""

    session = _session()
    owner = _user(session)
    project = _project(session, owner)
    test = _test(session, project, owner)
    target = _target(session, project, owner, "Own target")

    try:
        execution = create_execution(
            session,
            project.id,
            ExecutionCreate(test_id=test.id, target_id=target.id),
            owner,
        )
        assert execution.target_id == target.id
        assert execution.project_id == project.id
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_execution_rejects_test_from_another_project() -> None:
    """Already covered by existing logic; pinned here as a regression guard."""

    session = _session()
    victim = _user(session)
    attacker = _user(session)
    victim_project = _project(session, victim)
    attacker_project = _project(session, attacker)
    victim_test = _test(session, victim_project, victim)
    attacker_target = _target(session, attacker_project, attacker, "Attacker target")

    try:
        with pytest.raises(AssessmentNotFoundError):
            create_execution(
                session,
                attacker_project.id,
                ExecutionCreate(
                    test_id=victim_test.id,
                    target_id=attacker_target.id,
                ),
                attacker,
            )
    finally:
        for project in (victim_project, attacker_project):
            session.delete(project)
        session.commit()
        session.close()


def test_execution_allows_null_target_and_null_test() -> None:
    """Optional references stay optional."""

    session = _session()
    owner = _user(session)
    project = _project(session, owner)

    try:
        execution = create_execution(session, project.id, ExecutionCreate(), owner)
        assert execution.target_id is None
        assert execution.test_id is None
    finally:
        session.delete(project)
        session.commit()
        session.close()

"""Startup reconciliation of executions left in flight by a server restart."""

import asyncio
import logging
from uuid import uuid4

from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.project import Project
from app.models.user import User
from app.schemas import ExecutionCreate, ProjectCreate, SecurityTestCreate, UserCreate
from app.services.assessments import create_execution, create_security_test
from app.services.auth import register_user
from app.services.execution_recovery import (
    INTERRUPTED_MESSAGE,
    reconcile_stale_executions,
)
from app.services.projects import create_project
from sqlalchemy import select
from sqlalchemy.orm import Session


def _session() -> Session:
    return create_session_factory()()


def _setup(session: Session) -> tuple[User, Project]:
    owner = register_user(
        session,
        UserCreate(
            email=f"recovery-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )
    project = create_project(
        session,
        ProjectCreate(name=f"Recovery {uuid4()}"),
        owner_id=owner.id,
    )
    return owner, project


def _execution(
    session: Session,
    owner: User,
    project: Project,
    status: ExecutionStatus,
) -> Execution:
    test = create_security_test(
        session,
        project.id,
        SecurityTestCreate(
            name="Recovery Test",
            provider="openai_compatible",
            required_capabilities=["chat"],
        ),
        owner,
    )
    execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
    execution.status = status
    session.commit()
    return execution


def _reconciled_audit(session: Session, execution_id: object) -> AuditLog | None:
    return session.scalar(
        select(AuditLog).where(
            AuditLog.action == "execution.reconciled",
            AuditLog.resource_id == str(execution_id),
        )
    )


def test_pending_execution_is_recovered_as_failed() -> None:
    """An execution still PENDING at startup is orphaned and becomes FAILED."""

    session = _session()
    owner, project = _setup(session)
    try:
        execution = _execution(session, owner, project, ExecutionStatus.PENDING)

        recovered = reconcile_stale_executions(session)

        assert execution.id in recovered
        assert execution.status == ExecutionStatus.FAILED
        assert execution.result == ExecutionResult.INCONCLUSIVE
        assert execution.error == INTERRUPTED_MESSAGE
        assert execution.completed_at is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_running_execution_records_its_previous_status() -> None:
    """A stuck RUNNING execution is failed and the audit event names that state."""

    session = _session()
    owner, project = _setup(session)
    try:
        execution = _execution(session, owner, project, ExecutionStatus.RUNNING)

        recovered = reconcile_stale_executions(session)

        assert execution.id in recovered
        assert execution.status == ExecutionStatus.FAILED

        audit = _reconciled_audit(session, execution.id)
        assert audit is not None
        assert (audit.event_metadata or {})["previous_status"] == "running"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_terminal_executions_are_left_alone() -> None:
    """A finished execution is not touched by reconciliation."""

    session = _session()
    owner, project = _setup(session)
    try:
        execution = _execution(session, owner, project, ExecutionStatus.SUCCEEDED)

        recovered = reconcile_stale_executions(session)

        assert execution.id not in recovered
        session.refresh(execution)
        assert execution.status == ExecutionStatus.SUCCEEDED
        assert _reconciled_audit(session, execution.id) is None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_reconciliation_is_idempotent() -> None:
    """Running reconciliation twice does not recover the same execution again."""

    session = _session()
    owner, project = _setup(session)
    try:
        execution = _execution(session, owner, project, ExecutionStatus.RUNNING)

        first = reconcile_stale_executions(session)
        second = reconcile_stale_executions(session)

        assert execution.id in first
        assert execution.id not in second
    finally:
        session.delete(project)
        session.commit()
        session.close()


async def _enter_lifespan() -> None:
    from app import main

    async with main.lifespan(main.app):
        pass


def test_lifespan_never_blocks_startup_when_the_database_is_unreachable(monkeypatch) -> None:
    """A failed reconciliation must not keep the API from serving."""

    from app import main

    def _unavailable() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "create_session_factory", _unavailable)

    asyncio.run(_enter_lifespan())

    assert main.app.router.lifespan_context is not None


def test_lifespan_logs_how_many_executions_it_recovered(monkeypatch, caplog) -> None:
    """A successful reconciliation is visible in the startup log."""

    from app import main

    class _Session:
        def close(self) -> None:
            pass

    monkeypatch.setattr(main, "create_session_factory", lambda: lambda: _Session())
    monkeypatch.setattr(main, "reconcile_stale_executions", lambda session: [uuid4()])

    with caplog.at_level(logging.INFO, logger="aegis.startup"):
        asyncio.run(_enter_lifespan())

    assert "recovered 1 interrupted execution" in caplog.text

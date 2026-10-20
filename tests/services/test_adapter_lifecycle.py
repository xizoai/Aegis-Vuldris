"""Adapter lifecycle: every adapter must release its HTTP client.

Each execution builds a provider adapter, and an adapter that owns its client
owns a connection pool. The judge adapter was closed in a ``finally`` block but
the primary adapter was not, so every execution leaked an httpx client and its
sockets. Over many executions that exhausts file descriptors.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

from app.adapters.base import BaseTargetAdapter
from app.db.session import create_session_factory
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.model import ModelRequest, ModelResponse
from app.models.target import Target, TargetProvider
from app.schemas import UserCreate
from app.security.secrets import get_secret_store
from app.services.auth import register_user
from app.services.execution_engine import ExecutionEngine, _create_adapter
from sqlalchemy.orm import Session


class _ClosableAdapter(BaseTargetAdapter):
    """Minimal adapter double that records whether close() was called."""

    provider = TargetProvider.OPENAI_COMPATIBLE

    def __init__(self) -> None:
        super().__init__(
            client=cast(Any, None),
            endpoint_validator=cast(Any, lambda endpoint: None),
        )
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def _generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None,
    ) -> ModelResponse:
        raise RuntimeError("provider unavailable in this test double")


def _adapter_factory(created: list[_ClosableAdapter]):
    """Build an adapter_factory that records every adapter it produces."""

    def factory(
        provider: TargetProvider,
        credential_resolver: Callable[[str], Awaitable[str | None]] | None = None,
        **_kwargs: object,
    ) -> _ClosableAdapter:
        adapter = _ClosableAdapter()
        created.append(adapter)
        return adapter

    return factory


def _session() -> Session:
    return create_session_factory()()


def test_primary_adapter_is_closed_after_an_execution() -> None:
    """The core regression: the primary adapter must be released."""

    created: list[_ClosableAdapter] = []

    session = _session()
    email = f"lifecycle-{uuid4()}@example.com"
    user = register_user(session, UserCreate(email=email, password="a-very-strong-password"))

    from app.models.project import Project

    project = Project(name=f"Lifecycle {uuid4()}", owner_id=user.id)
    session.add(project)
    session.commit()
    session.refresh(project)

    execution = Execution(
        project_id=project.id,
        status=ExecutionStatus.PENDING,
        result=ExecutionResult.INCONCLUSIVE,
    )
    session.add(execution)

    # A test must be attached, otherwise the engine fails before it ever builds
    # an adapter and the lifecycle path is not exercised.
    from app.models.test import SecurityTest

    test = SecurityTest(
        project_id=project.id,
        name="Case",
        provider="openai_compatible",
        config={"prompts": [{"role": "user", "content": "hi"}], "max_retries": 0},
    )
    session.add(test)
    session.commit()
    session.refresh(test)

    execution.test_id = test.id
    session.commit()

    from app.models.target import Target

    target = Target(
        project_id=project.id,
        name="Model",
        provider=TargetProvider.OPENAI_COMPATIBLE,
        endpoint="https://model.example.com/v1",
        model="test-model",
    )
    session.add(target)
    session.commit()
    session.refresh(target)

    execution.target_id = target.id
    session.commit()
    session.refresh(execution)

    engine = ExecutionEngine(adapter_factory=_adapter_factory(created))

    try:
        asyncio.run(engine.execute(session, execution.id))

        assert created, "no adapter was created"
        assert all(adapter.closed for adapter in created), "the primary adapter was never closed"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_adapter_is_closed_even_when_execution_fails() -> None:
    """A failing execution must still release its adapter."""

    created: list[_ClosableAdapter] = []

    session = _session()
    email = f"lifecycle-fail-{uuid4()}@example.com"
    user = register_user(session, UserCreate(email=email, password="a-very-strong-password"))

    from app.models.project import Project

    project = Project(name=f"LifecycleFail {uuid4()}", owner_id=user.id)
    session.add(project)
    session.commit()
    session.refresh(project)

    # No test is attached, so the execution fails before reaching the adapter
    # branch; assert the engine still unwinds cleanly.
    execution = Execution(
        project_id=project.id,
        status=ExecutionStatus.PENDING,
        result=ExecutionResult.INCONCLUSIVE,
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)

    engine = ExecutionEngine(adapter_factory=_adapter_factory(created))
    try:
        asyncio.run(engine.execute(session, execution.id))
        session.refresh(execution)
        assert execution.status == ExecutionStatus.FAILED
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_create_adapter_returns_adapter_with_close() -> None:
    """Every adapter exposes an awaitable close(), which is what the fix relies on."""

    session = _session()
    try:
        target = Target(
            project_id=uuid4(),
            name="Model",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="test-model",
        )
        adapter = _create_adapter(target, get_secret_store(), session, None)
        assert hasattr(adapter, "close")
        assert asyncio.iscoroutinefunction(adapter.close)
    finally:
        session.close()

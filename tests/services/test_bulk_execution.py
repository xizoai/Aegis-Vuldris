"""Bulk execution of many selected tests against one target.

Selecting tests one at a time is not a usable workflow for a suite of 224. These
tests pin the behaviour that matters: every test must belong to the project, a
bad selection fails before anything is created, the runner bounds concurrency so
a local model is not overloaded, and each test is isolated from the others'
failures.
"""

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.errors import (
    AssessmentNotFoundError,
    ExecutionBindingError,
    PermissionDeniedError,
)
from app.db.session import create_session_factory
from app.models.target import TargetProvider
from app.models.user import User
from app.schemas import ProjectCreate, TargetCreate, UserCreate
from app.services.auth import register_user
from app.services.bulk_execution import (
    DEFAULT_BULK_CONCURRENCY,
    create_bulk_executions,
    run_bulk_executions,
    summarise_bulk_run,
)
from app.services.projects import create_project
from app.services.targets import create_target
from sqlalchemy.orm import Session

PASSWORD = "a-very-strong-password"


def _session() -> Session:
    return create_session_factory()()


def _run(coro: Any) -> Any:
    """Drive a coroutine synchronously, matching the adapter tests' pattern."""
    return asyncio.run(coro)


def _setup(session: Session):
    owner = register_user(
        session,
        UserCreate(email=f"bulk-{uuid4()}@example.com", password=PASSWORD),
    )
    project = create_project(session, ProjectCreate(name=f"Bulk {uuid4()}"), owner_id=owner.id)
    target = create_target(
        session,
        TargetCreate(
            project_id=project.id,
            name="Model",
            provider=TargetProvider.OLLAMA,
            endpoint="http://aegis-ollama:11434",
            model="qwen2.5:1.5b",
            authorization_attestation=True,
        ),
        project_id=project.id,
        user=owner,
    )
    return owner, project, target


def _make_test(session: Session, project, owner: User, name: str) -> UUID:
    from app.models.test import SecurityTest

    test = SecurityTest(
        project_id=project.id,
        name=name,
        provider="openai_compatible",
        config={"prompts": [{"role": "user", "content": "hi"}]},
    )
    session.add(test)
    session.commit()
    session.refresh(test)
    return test.id


def test_bulk_creates_one_execution_per_test() -> None:
    session = _session()
    owner, project, target = _setup(session)
    try:
        ids = [_make_test(session, project, owner, f"Case {i}") for i in range(4)]

        created = create_bulk_executions(session, project.id, owner, ids, target.id)

        assert len(created) == 4
        assert {execution.test_id for execution in created} == set(ids)
        assert all(execution.target_id == target.id for execution in created)
        assert all(execution.status.value == "pending" for execution in created)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_bulk_rejects_a_test_from_another_project() -> None:
    """One foreign test must fail the whole run, not silently skip it."""

    session = _session()
    owner, project, target = _setup(session)
    try:
        own = _make_test(session, project, owner, "Own")
        other_project = create_project(session, ProjectCreate(name="Other"), owner_id=owner.id)
        foreign = _make_test(session, other_project, owner, "Foreign")

        with pytest.raises(AssessmentNotFoundError):
            create_bulk_executions(session, project.id, owner, [own, foreign], target.id)

        # Nothing was created for the valid half either.
        from app.models.execution import Execution

        remaining = session.query(Execution).filter(Execution.project_id == project.id).all()
        assert remaining == []
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_bulk_requires_mutation_rights() -> None:
    """A viewer must not be able to queue a suite run."""

    session = _session()
    owner, project, target = _setup(session)
    try:
        viewer = register_user(
            session,
            UserCreate(email=f"bulk-viewer-{uuid4()}@example.com", password=PASSWORD),
        )
        viewer.is_active = True
        session.commit()
        from app.models.membership import ProjectMembership
        from app.models.user import UserRole

        session.add(
            ProjectMembership(project_id=project.id, user_id=viewer.id, role=UserRole.VIEWER)
        )
        viewer.role = UserRole.VIEWER
        session.commit()
        session.refresh(viewer)

        test_id = _make_test(session, project, owner, "Case")

        with pytest.raises(PermissionDeniedError):
            create_bulk_executions(session, project.id, viewer, [test_id], target.id)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_bulk_rejects_an_inactive_target() -> None:
    session = _session()
    owner, project, target = _setup(session)
    try:
        from app.models.target import TargetStatus

        target.status = TargetStatus.INACTIVE
        session.commit()
        test_id = _make_test(session, project, owner, "Case")

        with pytest.raises(ExecutionBindingError):
            create_bulk_executions(session, project.id, owner, [test_id], target.id)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_summary_counts_failures_and_findings() -> None:
    session = _session()
    owner, project, target = _setup(session)
    try:
        from app.models.execution import Execution
        from app.models.finding import Finding

        passed = _make_test(session, project, owner, "Passed")
        failed = _make_test(session, project, owner, "Failed")

        ok = Execution(
            project_id=project.id,
            test_id=passed,
            target_id=target.id,
            status="succeeded",
            result="pass",
        )
        bad = Execution(
            project_id=project.id,
            test_id=failed,
            target_id=target.id,
            status="failed",
            result="inconclusive",
            error="provider timeout",
        )
        session.add_all([ok, bad])
        session.commit()
        session.refresh(ok)
        session.refresh(bad)

        session.add(Finding(execution_id=ok.id, title="Leak", severity="high"))
        session.commit()

        outcome = summarise_bulk_run(session, [ok, bad], {passed: "Passed", failed: "Failed"})

        assert outcome.total == 2
        assert outcome.completed == 1
        assert outcome.failed == 1
        by_name = {r.test_name: r for r in outcome.results}
        assert by_name["Passed"].finding_count == 1
        assert by_name["Failed"].finding_count == 0
        assert by_name["Failed"].error == "provider timeout"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_summary_handles_an_empty_selection() -> None:
    session = _session()
    try:
        outcome = summarise_bulk_run(session, [], {})
        assert outcome.total == 0
        assert outcome.completed == 0
        assert outcome.results == []
    finally:
        session.close()


class _RecordingEngine:
    """Engine stub that records start/finish interleaving.

    ``run_single`` yields with a real sleep so a second coroutine can enter the
    semaphore while the first is still inside. Without a yield point the stub
    would complete synchronously and no overlap could ever be observed, which
    would make the concurrency test vacuous.
    """

    def __init__(self) -> None:
        self.running: set[UUID] = set()
        self.max_concurrent = 0
        self.ran: list[UUID] = []
        self.fail_for: UUID | None = None
        # Held closed to freeze a run mid-flight; set it to let the run proceed.
        self.gate = asyncio.Event()
        self.gate.set()

    async def run_single(self, execution_id: UUID) -> None:
        self.running.add(execution_id)
        self.max_concurrent = max(self.max_concurrent, len(self.running))
        try:
            # A real yield so a second coroutine can enter the semaphore while
            # this one is still inside. Without it the stub would finish
            # synchronously and no overlap could ever be observed, which would
            # make the concurrency assertion vacuous.
            await asyncio.sleep(0.02)
            await self.gate.wait()
            if execution_id == self.fail_for:
                raise RuntimeError("provider exploded")
            self.ran.append(execution_id)
        finally:
            self.running.discard(execution_id)


def test_runner_bounds_concurrency() -> None:
    """A suite against a local model must not fire every request at once."""

    engine = _RecordingEngine()
    ids = [uuid4() for _ in range(6)]

    async def scenario() -> None:
        task = await run_bulk_executions(engine, ids, concurrency=2)
        await asyncio.wait_for(task, timeout=5)

    _run(scenario())

    # Peak overlap across the whole run never exceeded the cap.
    assert engine.max_concurrent == 2
    assert len(engine.ran) == 6


def test_runner_returns_before_the_run_finishes() -> None:
    """A 202 must be possible, so starting the run cannot block the caller."""

    engine = _RecordingEngine()
    engine.gate.clear()

    async def scenario() -> bool:
        task = await run_bulk_executions(engine, [uuid4(), uuid4()], concurrency=2)
        # Control is already back here with nothing finished: the gate holds the
        # wave open, so an awaited run would still be blocked at this point.
        returned_early = not task.done() and engine.ran == []
        engine.gate.set()
        await asyncio.wait_for(task, timeout=5)
        return returned_early

    assert _run(scenario()) is True


def test_runner_keeps_a_strong_reference_to_the_task() -> None:
    """asyncio holds only a weak reference; an untracked run could vanish."""

    from app.services import bulk_execution

    engine = _RecordingEngine()
    engine.gate.clear()

    async def scenario() -> tuple[bool, bool]:
        task = await run_bulk_executions(engine, [uuid4()], concurrency=1)
        tracked_while_running = task in bulk_execution._TRACKED_TASKS
        engine.gate.set()
        await asyncio.wait_for(task, timeout=5)
        return tracked_while_running, task not in bulk_execution._TRACKED_TASKS

    tracked_while_running, dropped_when_done = _run(scenario())
    assert tracked_while_running is True
    # The callback drops it once done, so the set does not grow unboundedly.
    assert dropped_when_done is True


def test_runner_isolates_a_failing_execution() -> None:
    """One provider failure must not strand the rest of the selection."""

    engine = _RecordingEngine()
    good = [uuid4(), uuid4()]
    engine.fail_for = good[0]

    async def scenario() -> None:
        task = await run_bulk_executions(engine, good + [uuid4()], concurrency=3)
        # gather re-raises, but every other execution still ran to completion.
        with pytest.raises(RuntimeError):
            await asyncio.wait_for(task, timeout=5)

    _run(scenario())

    assert good[1] in engine.ran
    assert len(engine.ran) == 2


def test_default_concurrency_is_small_for_a_local_model() -> None:
    """The default must not be large enough to overload a 1.5B model."""

    assert DEFAULT_BULK_CONCURRENCY <= 4

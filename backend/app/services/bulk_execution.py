"""Bulk execution: run many selected tests against one target.

Selecting tests one at a time is not a realistic workflow for a suite of 224.
This creates every requested execution, runs them, and reports what happened
to each one.

Concurrency is deliberately bounded. Firing 224 requests at a local 1.5B model
simultaneously would exhaust its request queue and turn almost every run into a
timeout, which would look like 224 failures. The default limit is low enough to
be safe against a small local model and high enough to overlap provider latency.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AssessmentNotFoundError
from app.models.execution import Execution, ExecutionStatus
from app.models.finding import Finding
from app.models.project import Project
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas.assessment import BulkExecutionResult, ExecutionCreate
from app.services.assessments import (
    _require_project_target,
    _require_project_test,
    create_execution,
    validate_execution_binding,
)
from app.services.projects import ensure_project_access

# Provider calls per bulk run. Small enough that a local model accepts them.
DEFAULT_BULK_CONCURRENCY = 2


@dataclass
class BulkRunOutcome:
    """Outcome of a bulk run."""

    total: int = 0
    completed: int = 0
    failed: int = 0
    results: list[BulkExecutionResult] = field(default_factory=list)


def create_bulk_executions(
    session: Session,
    project_id: UUID,
    user: User,
    test_ids: list[UUID],
    target_id: UUID,
) -> list[Execution]:
    """Create one execution per test, all belonging to the same project.

    Raises before creating anything if any test is missing or belongs to another
    project, so a caller never sees a partially-created bulk run.
    """

    project = session.get(Project, project_id)
    if project is None:
        raise AssessmentNotFoundError()

    # Writing many rows is a mutating operation, not a read.
    ensure_project_access(session, user, project, "update")

    for test_id in test_ids:
        _require_project_test(session, project_id, test_id)
    target = _require_project_target(session, project_id, target_id)

    created: list[Execution] = []
    for test_id in test_ids:
        test = session.get(SecurityTest, test_id)
        validate_execution_binding(test, target)
        created.append(
            create_execution(
                session,
                project_id,
                ExecutionCreate(test_id=test_id, target_id=target_id),
                user,
            )
        )
    return created


# Strong references to in-flight bulk runs. asyncio only keeps weak references,
# so without this a run could be garbage-collected after the request returns.
_TRACKED_TASKS: set[asyncio.Task[None]] = set()


async def run_bulk_executions(
    engine,
    execution_ids: list[UUID],
    *,
    concurrency: int = DEFAULT_BULK_CONCURRENCY,
) -> asyncio.Task[None]:
    """Start a bounded-concurrency run of every execution and return its task.

    The engine's own ``schedule`` fires one task per execution with no bound,
    which is wrong for a suite run against a small model: 224 simultaneous
    requests exhaust its queue and turn almost every run into a timeout, which
    reads as 224 failures.

    Returning the task (rather than being awaited) is what lets a request return
    immediately while the run continues. The caller must keep a reference: the
    event loop only holds a weak one, so a run nobody references could be
    collected mid-flight. ``_TRACKED_TASKS`` does that.
    """

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def guarded(execution_id: UUID) -> None:
        async with semaphore:
            await engine.run_single(execution_id)

    async def run_all() -> None:
        await asyncio.gather(*(guarded(execution_id) for execution_id in execution_ids))

    task = asyncio.create_task(run_all(), name="bulk-execution")
    _TRACKED_TASKS.add(task)
    task.add_done_callback(_TRACKED_TASKS.discard)
    return task


def summarise_bulk_run(
    session: Session,
    executions: Sequence[Execution],
    test_names: dict[UUID, str],
) -> BulkRunOutcome:
    """Build the per-test outcome summary from finished executions.

    ``test_id`` is nullable on the row: deleting a security test nulls the
    executions that referenced it. A bulk run always sets one, so a null here
    means the test was deleted underneath a run in flight — reported as unknown
    rather than crashed on, because the run did still happen.
    """

    outcome = BulkRunOutcome(total=len(executions))

    for execution in executions:
        finding_count = len(
            session.scalars(select(Finding.id).where(Finding.execution_id == execution.id)).all()
        )

        result = BulkExecutionResult(
            test_id=execution.test_id,
            test_name=(
                "Deleted test"
                if execution.test_id is None
                else test_names.get(execution.test_id, "Unknown test")
            ),
            execution_id=execution.id,
            status=execution.status.value,
            result=execution.result.value if execution.result else None,
            error=execution.error,
            finding_count=finding_count,
        )
        outcome.results.append(result)

        if execution.status is ExecutionStatus.FAILED:
            outcome.failed += 1
        else:
            outcome.completed += 1

    return outcome


__all__ = [
    "DEFAULT_BULK_CONCURRENCY",
    "BulkRunOutcome",
    "create_bulk_executions",
    "run_bulk_executions",
    "summarise_bulk_run",
]

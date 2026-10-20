"""Recovery of executions left in flight by a server restart.

The execution engine runs each execution as an in-process asyncio task and keeps
its task registry in memory (``app.services.execution_engine``). A restart drops
that registry, so any execution still ``PENDING`` or ``RUNNING`` when the process
comes back belongs to a task that no longer exists and can never reach a terminal
state on its own.

Left alone, such an execution is misleading: ``PENDING`` reads as "queued and
about to run" and ``RUNNING`` reads as "in progress", when in fact neither will
ever change. This reconciles them at startup by recording the terminal ``FAILED``
state they actually reached, with a reason that names the cause.

There is no partial work to repair: execution steps are only written once a turn
has succeeded (see ``execution_engine``), so a crashed run leaves steps for the
turns it completed and none for the turn it died in.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.services.audit import record_audit_event

INTERRUPTED_MESSAGE = "interrupted by a server restart before completion"

# The two statuses that mean "a task owns this and it is expected to move".
_IN_FLIGHT: tuple[ExecutionStatus, ...] = (
    ExecutionStatus.PENDING,
    ExecutionStatus.RUNNING,
)


def reconcile_stale_executions(
    session: Session,
    *,
    now: datetime | None = None,
) -> list[UUID]:
    """Mark executions left in flight by a previous process run as FAILED.

    Returns the ids that were recovered. Idempotent: once nothing is in flight,
    a second call is a no-op. Each recovery writes an ``execution.reconciled``
    audit event recording the status the execution was stuck in, so the change
    is attributable and its cause is on the record.
    """

    reference = now or datetime.now(UTC)
    stale = list(session.scalars(select(Execution).where(Execution.status.in_(_IN_FLIGHT))).all())
    if not stale:
        return []

    # Capture the prior status before mutating, for the audit trail.
    recovered: list[tuple[Execution, ExecutionStatus]] = [(e, e.status) for e in stale]

    for execution, _previous in recovered:
        execution.status = ExecutionStatus.FAILED
        execution.result = ExecutionResult.INCONCLUSIVE
        execution.error = INTERRUPTED_MESSAGE
        execution.completed_at = reference

    session.commit()

    for execution, previous in recovered:
        record_audit_event(
            session,
            actor_id=execution.created_by,
            action="execution.reconciled",
            resource_type="execution",
            resource_id=str(execution.id),
            event_metadata={"previous_status": previous.value},
        )

    return [execution.id for execution, _previous in recovered]


__all__ = ["INTERRUPTED_MESSAGE", "reconcile_stale_executions"]

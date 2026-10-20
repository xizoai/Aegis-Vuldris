"""Durable external-scan queue operations for AegisAI.

Scans outlive the API process: their state lives in ``external_scans`` and a
separate runner claims jobs. The API stays the only writer. Claiming uses
``FOR UPDATE SKIP LOCKED`` so two runners polling at the same time receive
different jobs instead of racing for the same one.

Completion is accepted only from ``running``. A runner that reports twice (for
example after its network reply was lost) gets a conflict rather than a second
terminal transition, so a job completes at most once.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import (
    AssessmentNotFoundError,
    ProjectNotFoundError,
    ScanNotFoundError,
    ScanStateConflictError,
)
from app.models.external_scan import ExternalScan, ExternalScanStatus
from app.models.finding import Finding
from app.models.project import Project
from app.models.target import Target
from app.models.user import User
from app.schemas.scan import ScanCompleteRequest, ScanCreate
from app.services.audit import record_audit_event
from app.services.projects import ensure_project_access
from app.services.scan_ingestion import IngestSummary, ingest_scan_results

_TERMINAL_STATUSES = frozenset(
    {
        ExternalScanStatus.COMPLETED,
        ExternalScanStatus.FAILED,
        ExternalScanStatus.CANCELLED,
    }
)


def _require_project(session: Session, user: User, project_id: UUID, operation: str) -> Project:
    """Authorize an operation on the scan's owning project."""

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, operation)
    return project


def create_scan(
    session: Session,
    project_id: UUID,
    payload: ScanCreate,
    user: User,
) -> ExternalScan:
    """Queue an external scan for a target in an authorized project."""

    _require_project(session, user, project_id, "create")

    target = session.get(Target, payload.target_id)
    if target is None or target.project_id != project_id:
        raise AssessmentNotFoundError()

    scan = ExternalScan(
        project_id=project_id,
        target_id=target.id,
        tool=payload.tool,
        config=payload.config,
        status=ExternalScanStatus.QUEUED,
        created_by=user.id,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    record_audit_event(
        session,
        actor_id=user.id,
        action="scan.queued",
        resource_type="scan",
        resource_id=str(scan.id),
        event_metadata={
            "project_id": str(project_id),
            "target_id": str(target.id),
            "tool": scan.tool.value,
        },
    )

    return scan


def get_scan_for_user(session: Session, scan_id: UUID, user: User) -> ExternalScan:
    """Return a scan the user can read through its project."""

    scan = session.get(ExternalScan, scan_id)
    if scan is None:
        raise ScanNotFoundError()

    _require_project(session, user, scan.project_id, "read")
    return scan


def list_scans_for_user(session: Session, project_id: UUID, user: User) -> list[ExternalScan]:
    """Return a project's scans, newest first, if the user can read it."""

    _require_project(session, user, project_id, "read")

    return list(
        session.scalars(
            select(ExternalScan)
            .where(ExternalScan.project_id == project_id)
            .order_by(ExternalScan.created_at.desc())
        ).all()
    )


def list_scan_findings(session: Session, scan_id: UUID) -> list[Finding]:
    """Return a scan's findings, most severe first.

    Severity order is the enum's declaration order, so the same ordering works
    for native findings; within a tier the report's own order is preserved.
    """

    return list(
        session.scalars(
            select(Finding)
            .where(Finding.external_scan_id == scan_id)
            .order_by(Finding.severity.desc(), Finding.created_at)
        ).all()
    )


def cancel_scan(session: Session, scan_id: UUID, user: User) -> ExternalScan:
    """Cancel a queued or running scan.

    Cancelling a running scan clears the lease; a runner that finishes anyway is
    rejected by the completion state check, which is what stops a cancelled scan
    from being resurrected.
    """

    scan = get_scan_for_user(session, scan_id, user)
    _require_project(session, user, scan.project_id, "cancel")

    if scan.status in _TERMINAL_STATUSES:
        raise ScanStateConflictError(f"scan is already {scan.status.value}")

    scan.status = ExternalScanStatus.CANCELLED
    scan.finished_at = datetime.now(UTC)
    scan.claimed_at = None
    scan.claim_id = None
    session.commit()
    session.refresh(scan)

    record_audit_event(
        session,
        actor_id=user.id,
        action="scan.cancelled",
        resource_type="scan",
        resource_id=str(scan.id),
        event_metadata={"project_id": str(scan.project_id), "tool": scan.tool.value},
    )

    return scan


def requeue_expired_claims(
    session: Session,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> int:
    """Return abandoned claims to the queue and report how many were requeued.

    A runner that dies mid-scan leaves a ``running`` row with no one working on
    it. Once its lease expires it goes back to ``queued`` and ``attempt_count``
    eventually shows the churn. Phase 5 adds runner heartbeats so long scans can
    extend the lease instead of relying on a generous default.
    """

    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(seconds=lease_seconds)

    stale = list(
        session.scalars(
            select(ExternalScan).where(
                ExternalScan.status == ExternalScanStatus.RUNNING,
                ExternalScan.claimed_at.is_not(None),
                ExternalScan.claimed_at < cutoff,
            )
        ).all()
    )

    if not stale:
        return 0

    for scan in stale:
        scan.status = ExternalScanStatus.QUEUED
        scan.claimed_at = None
        scan.claim_id = None
        scan.started_at = None
        scan.error = "runner claim expired; scan requeued"

    session.commit()
    return len(stale)


def claim_next_scan(
    session: Session,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> ExternalScan | None:
    """Atomically claim the oldest queued scan, or return None when idle.

    ``SKIP LOCKED`` is what makes this safe with more than one runner: a row
    already being claimed is skipped rather than waited on, so pollers do not
    serialize behind each other.
    """

    reference = now or datetime.now(UTC)
    requeue_expired_claims(session, lease_seconds=lease_seconds, now=reference)

    scan = session.scalar(
        select(ExternalScan)
        .where(ExternalScan.status == ExternalScanStatus.QUEUED)
        .order_by(ExternalScan.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    if scan is None:
        return None

    scan.status = ExternalScanStatus.RUNNING
    scan.started_at = reference
    scan.claimed_at = reference
    scan.claim_id = uuid4().hex
    scan.attempt_count += 1
    session.commit()
    session.refresh(scan)

    return scan


def complete_scan(
    session: Session,
    scan_id: UUID,
    payload: ScanCompleteRequest,
    *,
    now: datetime | None = None,
) -> ExternalScan:
    """Record a runner's terminal report for a running scan.

    A second report, or a report for a scan that was cancelled, raises a
    conflict. This is the exactly-once boundary: only the first transition out
    of ``running`` succeeds.

    The payload's normalized verdicts are ingested in the same transaction as
    the transition, so a completed scan and the findings from its report are
    either both visible or both absent.
    """

    scan = session.get(ExternalScan, scan_id)
    if scan is None:
        raise ScanNotFoundError()

    if scan.status != ExternalScanStatus.RUNNING:
        raise ScanStateConflictError(
            f"scan is {scan.status.value}; only a running scan can be completed"
        )

    scan.status = (
        ExternalScanStatus.COMPLETED if payload.status == "completed" else ExternalScanStatus.FAILED
    )
    scan.finished_at = now or datetime.now(UTC)
    scan.claimed_at = None
    scan.claim_id = None
    if payload.tool_version is not None:
        scan.tool_version = payload.tool_version
    scan.external_run_id = payload.external_run_id
    scan.report_path = payload.report_path
    scan.error = payload.error

    # Ingest before the commit so the terminal transition and its findings are
    # one transaction: a completed scan is never left without the findings its
    # report holds. A partial run still ingests what it produced, which is why
    # a failed scan can carry findings too.
    summary: IngestSummary = ingest_scan_results(session, scan, payload.results)

    session.commit()
    session.refresh(scan)

    record_audit_event(
        session,
        actor_id=scan.created_by,
        action=f"scan.{scan.status.value}",
        resource_type="scan",
        resource_id=str(scan.id),
        event_metadata={
            "project_id": str(scan.project_id),
            "tool": scan.tool.value,
            "tool_version": scan.tool_version,
            "external_run_id": scan.external_run_id,
            "findings": summary.findings,
            "probes_passed": summary.passes,
            "probes_inconclusive": summary.inconclusive,
        },
    )

    return scan


__all__ = [
    "cancel_scan",
    "claim_next_scan",
    "complete_scan",
    "create_scan",
    "get_scan_for_user",
    "list_scan_findings",
    "list_scans_for_user",
    "requeue_expired_claims",
]

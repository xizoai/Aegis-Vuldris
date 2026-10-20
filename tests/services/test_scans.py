"""Durable external scan queue tests for AegisAI."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.api.errors import (
    AssessmentNotFoundError,
    PermissionDeniedError,
    ScanNotFoundError,
    ScanStateConflictError,
)
from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.external_scan import ExternalScan, ExternalScanStatus, ExternalScanTool
from app.models.project import Project
from app.models.target import Target, TargetProvider
from app.models.user import User
from app.schemas import (
    ProjectCreate,
    ScanCompleteRequest,
    ScanCreate,
    TargetCreate,
    UserCreate,
)
from app.services.auth import register_user
from app.services.projects import create_project
from app.services.scans import (
    cancel_scan,
    claim_next_scan,
    complete_scan,
    create_scan,
    get_scan_for_user,
    requeue_expired_claims,
)
from app.services.targets import create_target
from sqlalchemy import select
from sqlalchemy.orm import Session


def _session() -> Session:
    return create_session_factory()()


def _register(session: Session) -> User:
    return register_user(
        session,
        UserCreate(
            email=f"scan-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )


def _project(session: Session, owner: User) -> Project:
    return create_project(
        session,
        ProjectCreate(name=f"Scan Project {uuid4()}"),
        owner_id=owner.id,
    )


def _target(session: Session, project_id: UUID, owner: User) -> Target:
    return create_target(
        session,
        TargetCreate(
            project_id=project_id,
            name=f"Scan Target {uuid4()}",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="test-model",
            capabilities=["chat"],
            authorization_attestation=True,
        ),
        project_id,
        owner,
    )


def _scan(
    session: Session,
    project_id: UUID,
    target_id: UUID,
    owner: User,
    tool: ExternalScanTool = ExternalScanTool.GARAK,
) -> ExternalScan:
    return create_scan(
        session,
        project_id,
        ScanCreate(target_id=target_id, tool=tool, config={"probes": ["prompt_injection"]}),
        owner,
    )


def _require_clean_queue(session: Session) -> None:
    """Skip claim-dependent tests if another test left work behind."""

    pending = session.scalar(
        select(ExternalScan).where(
            ExternalScan.status.in_([ExternalScanStatus.QUEUED, ExternalScanStatus.RUNNING])
        )
    )
    if pending is not None:
        pytest.skip("queue already contains work from another test")


def _dispose(session: Session, *project_ids: UUID) -> None:
    """Delete test projects (cascading to scans and targets) and close."""

    for project_id in project_ids:
        project = session.get(Project, project_id)
        if project is not None:
            session.delete(project)
    session.commit()
    session.close()


def test_create_scan_queues_it_and_audits() -> None:
    session = _session()
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)

        assert scan.status == ExternalScanStatus.QUEUED
        assert scan.attempt_count == 0
        assert scan.tool == ExternalScanTool.GARAK
        assert scan.config == {"probes": ["prompt_injection"]}
        assert scan.created_by == owner.id

        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "scan.queued",
                AuditLog.resource_id == str(scan.id),
            )
        )
        assert audit is not None
        assert audit.actor_id == owner.id
    finally:
        _dispose(session, project.id)


def test_create_scan_rejects_a_target_from_another_project() -> None:
    session = _session()
    owner = _register(session)
    project = _project(session, owner)
    other_project = _project(session, owner)
    target = _target(session, other_project.id, owner)

    try:
        with pytest.raises(AssessmentNotFoundError):
            _scan(session, project.id, target.id, owner)
    finally:
        _dispose(session, project.id, other_project.id)


def test_create_scan_requires_project_membership() -> None:
    session = _session()
    owner = _register(session)
    stranger = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        with pytest.raises(PermissionDeniedError):
            _scan(session, project.id, target.id, stranger)
    finally:
        _dispose(session, project.id)


def test_claim_marks_the_scan_running() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)

        claimed = claim_next_scan(session, lease_seconds=60)

        assert claimed is not None
        assert claimed.id == scan.id
        assert claimed.status == ExternalScanStatus.RUNNING
        assert claimed.started_at is not None
        assert claimed.claimed_at is not None
        assert claimed.attempt_count == 1
    finally:
        _dispose(session, project.id)


def test_claim_takes_the_oldest_queued_scan_first() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        older = _scan(session, project.id, target.id, owner)
        older.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        session.commit()

        newer = _scan(session, project.id, target.id, owner)
        newer.created_at = datetime(2026, 1, 2, tzinfo=UTC)
        session.commit()

        first = claim_next_scan(session, lease_seconds=60)
        second = claim_next_scan(session, lease_seconds=60)

        assert first is not None and first.id == older.id
        assert second is not None and second.id == newer.id
    finally:
        _dispose(session, project.id)


def test_claim_returns_none_when_no_work_is_queued() -> None:
    session = _session()
    _require_clean_queue(session)

    try:
        assert claim_next_scan(session, lease_seconds=60) is None
    finally:
        session.close()


def test_queued_scan_survives_a_new_session() -> None:
    """State is in the database, not the process, so a restart loses nothing."""

    setup_session = _session()
    _require_clean_queue(setup_session)
    owner = _register(setup_session)
    project = _project(setup_session, owner)
    target = _target(setup_session, project.id, owner)
    scan = _scan(setup_session, project.id, target.id, owner)
    scan_id = scan.id
    setup_session.close()

    session = _session()
    try:
        claimed = claim_next_scan(session, lease_seconds=60)

        assert claimed is not None
        assert claimed.id == scan_id
    finally:
        _dispose(session, project.id)


def test_complete_records_the_terminal_state_and_audit() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)
        claim_next_scan(session, lease_seconds=60)

        completed = complete_scan(
            session,
            scan.id,
            ScanCompleteRequest(
                status="completed",
                tool_version="0.17.1",
                external_run_id="garak-run-1",
                report_path="/var/lib/aegis/reports/garak-run-1.jsonl",
            ),
        )

        assert completed.status == ExternalScanStatus.COMPLETED
        assert completed.finished_at is not None
        assert completed.claimed_at is None
        assert completed.tool_version == "0.17.1"
        assert completed.external_run_id == "garak-run-1"
        assert completed.report_path == "/var/lib/aegis/reports/garak-run-1.jsonl"

        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "scan.completed",
                AuditLog.resource_id == str(scan.id),
            )
        )
        assert audit is not None
    finally:
        _dispose(session, project.id)


def test_second_completion_is_rejected() -> None:
    """A duplicate runner report cannot transition the scan twice."""

    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)
        claim_next_scan(session, lease_seconds=60)

        first = complete_scan(
            session,
            scan.id,
            ScanCompleteRequest(status="completed", external_run_id="first"),
        )

        with pytest.raises(ScanStateConflictError):
            complete_scan(
                session,
                scan.id,
                ScanCompleteRequest(status="failed", external_run_id="second"),
            )

        session.refresh(first)
        assert first.status == ExternalScanStatus.COMPLETED
        assert first.external_run_id == "first"
    finally:
        _dispose(session, project.id)


def test_complete_rejects_a_queued_scan() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)

        with pytest.raises(ScanStateConflictError):
            complete_scan(session, scan.id, ScanCompleteRequest(status="completed"))
    finally:
        _dispose(session, project.id)


def test_cancel_queued_scan_removes_it_from_claiming() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)

        cancelled = cancel_scan(session, scan.id, owner)

        assert cancelled.status == ExternalScanStatus.CANCELLED
        assert cancelled.finished_at is not None

        claimed = claim_next_scan(session, lease_seconds=60)
        assert claimed is None or claimed.id != scan.id
    finally:
        _dispose(session, project.id)


def test_cancel_completed_scan_conflicts() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)
        claim_next_scan(session, lease_seconds=60)
        complete_scan(session, scan.id, ScanCompleteRequest(status="completed"))

        with pytest.raises(ScanStateConflictError):
            cancel_scan(session, scan.id, owner)
    finally:
        _dispose(session, project.id)


def test_expired_claim_is_requeued_and_can_be_claimed_again() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)
        claimed_at = datetime(2026, 1, 1, tzinfo=UTC)
        claim_next_scan(session, lease_seconds=60, now=claimed_at)

        requeued = requeue_expired_claims(
            session,
            lease_seconds=60,
            now=claimed_at + timedelta(seconds=61),
        )

        assert requeued == 1
        session.refresh(scan)
        assert scan.status == ExternalScanStatus.QUEUED
        assert scan.claimed_at is None

        reclaimed = claim_next_scan(
            session,
            lease_seconds=60,
            now=claimed_at + timedelta(seconds=62),
        )
        assert reclaimed is not None
        assert reclaimed.id == scan.id
        assert reclaimed.attempt_count == 2
    finally:
        _dispose(session, project.id)


def test_active_claim_is_not_requeued() -> None:
    session = _session()
    _require_clean_queue(session)
    owner = _register(session)
    project = _project(session, owner)
    target = _target(session, project.id, owner)

    try:
        scan = _scan(session, project.id, target.id, owner)
        claimed_at = datetime(2026, 1, 1, tzinfo=UTC)
        claim_next_scan(session, lease_seconds=60, now=claimed_at)

        requeued = requeue_expired_claims(
            session,
            lease_seconds=60,
            now=claimed_at + timedelta(seconds=30),
        )

        assert requeued == 0
        session.refresh(scan)
        assert scan.status == ExternalScanStatus.RUNNING
    finally:
        _dispose(session, project.id)


def test_get_scan_for_user_rejects_unknown_id() -> None:
    session = _session()
    owner = _register(session)

    try:
        with pytest.raises(ScanNotFoundError):
            get_scan_for_user(session, uuid4(), owner)
    finally:
        session.close()

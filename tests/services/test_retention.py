"""Evidence retention and deletion.

Retention has to be finite and enforceable, otherwise evidence — the most
sensitive data Aegis Vuldris holds — accumulates indefinitely. A project declares how
long its evidence is kept, and a cleanup pass removes what has aged out.

These tests pin the boundary behaviour: what is removed, what is kept, and that
deletion is scoped to the project and audited.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.db.session import create_session_factory
from app.models.evidence import Evidence, Sensitivity
from app.models.execution import Execution
from app.models.finding import Finding
from app.models.project import Project
from app.models.report import Report
from app.schemas import ProjectCreate, UserCreate
from app.services.auth import register_user
from app.services.projects import create_project
from app.services.retention import (
    DEFAULT_RETENTION_DAYS,
    cleanup_expired_evidence,
    project_retention_cutoff,
)
from sqlalchemy.orm import Session


def _session() -> Session:
    return create_session_factory()()


def _project(session: Session, retention_days: int):
    owner = register_user(
        session,
        UserCreate(email=f"ret-{uuid4()}@example.com", password="a-very-strong-password"),
    )
    project = create_project(session, ProjectCreate(name=f"Retention {uuid4()}"), owner_id=owner.id)
    project.evidence_retention_days = retention_days
    session.commit()
    session.refresh(project)
    return owner, project


def _aged_evidence(session: Session, project: Project, age_days: int) -> Evidence:
    """Create an evidence record with a controlled creation time."""

    execution = Execution(project_id=project.id)
    session.add(execution)
    session.commit()
    finding = Finding(execution_id=execution.id, title="Leak", severity="critical")
    session.add(finding)
    session.commit()

    record = Evidence(
        finding_id=finding.id,
        kind="model_response",
        content={"output": "x"},
        sensitivity=int(Sensitivity.RESTRICTED),
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    # Backdate so the row is unambiguously past or within the cutoff.
    record.created_at = datetime.now(UTC) - timedelta(days=age_days)
    session.commit()
    return record


def test_default_retention_is_finite() -> None:
    """Retention must have a bounded default, not mean "forever"."""

    assert 0 < DEFAULT_RETENTION_DAYS <= 365


def test_project_retention_defaults_to_the_default_window() -> None:
    session = _session()
    owner = register_user(
        session,
        UserCreate(email=f"retdef-{uuid4()}@example.com", password="a-very-strong-password"),
    )
    project = create_project(session, ProjectCreate(name="Default"), owner_id=owner.id)
    session.commit()
    session.refresh(project)
    try:
        assert project.evidence_retention_days == DEFAULT_RETENTION_DAYS
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cutoff_is_derived_from_the_project_window() -> None:
    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        # Inject the clock: deriving the cutoff from the wall clock and then
        # comparing against a second reading makes the boundary flaky by the
        # microseconds between the two calls.
        now = datetime.now(UTC)
        cutoff = project_retention_cutoff(project, now=now)
        assert cutoff == now - timedelta(days=30)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cleanup_removes_expired_evidence() -> None:
    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        old = _aged_evidence(session, project, age_days=90)
        assert session.get(Evidence, old.id) is not None

        result = cleanup_expired_evidence(session)

        assert result.evidence_deleted >= 1
        assert session.get(Evidence, old.id) is None
        # The finding is the assessment result and must survive its evidence.
        assert session.get(Finding, old.finding_id) is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cleanup_keeps_evidence_inside_the_window() -> None:
    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        recent = _aged_evidence(session, project, age_days=1)

        cleanup_expired_evidence(session)

        assert session.get(Evidence, recent.id) is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cleanup_ignores_projects_without_a_retention_window() -> None:
    """A project set to keep evidence forever must not be swept."""

    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        old = _aged_evidence(session, project, age_days=3650)
        project.evidence_retention_days = 0  # 0 means keep indefinitely
        session.commit()

        cleanup_expired_evidence(session)

        assert session.get(Evidence, old.id) is not None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cleanup_removes_expired_report_artifacts(tmp_path: Path) -> None:
    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        artifact = tmp_path / "old-report.json"
        artifact.write_text("{}", encoding="utf-8")

        report = Report(
            project_id=project.id,
            title="Old",
            format="json",
            path=str(artifact),
            version=1,
        )
        session.add(report)
        session.commit()

        report.created_at = datetime.now(UTC) - timedelta(days=90)
        session.commit()

        result = cleanup_expired_evidence(session, report_dir=tmp_path)

        assert result.artifacts_deleted >= 1
        assert not artifact.exists()
        # The row survives as a record, with its path cleared so a stale
        # download cannot be served.
        surviving = session.get(Report, report.id)
        assert surviving is not None
        assert surviving.path == ""
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cleanup_is_idempotent() -> None:
    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        _aged_evidence(session, project, age_days=90)

        first = cleanup_expired_evidence(session)
        second = cleanup_expired_evidence(session)

        assert first.evidence_deleted >= 1
        assert second.evidence_deleted == 0
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_dry_run_reports_without_deleting() -> None:
    """--dry-run must be a real no-op, not a flag that still deletes."""

    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        old = _aged_evidence(session, project, age_days=90)

        result = cleanup_expired_evidence(session, dry_run=True)

        assert result.evidence_deleted >= 1
        assert session.get(Evidence, old.id) is not None, "dry run deleted evidence"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_cleanup_writes_an_audit_event() -> None:
    session = _session()
    owner, project = _project(session, retention_days=30)
    try:
        from app.models.audit_log import AuditLog
        from sqlalchemy import select as sa_select

        _aged_evidence(session, project, age_days=90)
        result = cleanup_expired_evidence(session)

        events = session.scalars(
            sa_select(AuditLog).where(AuditLog.action == "evidence.retention_purged")
        ).all()
        assert events, "retention purge was not audited"
        metadata = events[-1].event_metadata or {}
        assert metadata.get("evidence_deleted") == result.evidence_deleted
    finally:
        session.delete(project)
        session.commit()
        session.close()

"""Evidence retention and deletion.

Evidence is the most sensitive data Aegis Vuldris holds: it contains the prompts
sent and the responses that produced a finding. Retention therefore has to be
finite and enforced, not merely documented.

Each project declares how long its evidence is kept. A cleanup pass removes
evidence rows and generated report artifacts that have aged past that window.

Deliberate limitation: deleting a file from a report volume is an unlink, not a
secure erase. On copy-on-write filesystems and SSDs the old blocks may persist.
Guaranteeing otherwise needs volume encryption with key destruction, which is a
deployment concern. See ``docs/data-retention.md``.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
from app.models.execution import Execution
from app.models.finding import Finding
from app.models.project import DEFAULT_EVIDENCE_RETENTION_DAYS, Project
from app.models.report import Report
from app.services.audit import record_audit_event

# Re-exported so callers need only this module for the default.
DEFAULT_RETENTION_DAYS = DEFAULT_EVIDENCE_RETENTION_DAYS


@dataclass(frozen=True)
class CleanupResult:
    """What a cleanup pass removed."""

    projects_scanned: int
    evidence_deleted: int
    reports_expired: int
    artifacts_deleted: int
    artifacts_missing: int


def project_retention_cutoff(project: Project, *, now: datetime | None = None) -> datetime | None:
    """Return the instant before which a project keeps nothing.

    ``None`` means the project keeps evidence indefinitely.
    """

    days = project.evidence_retention_days or 0
    if days <= 0:
        return None
    return (now or datetime.now(UTC)) - timedelta(days=days)


def cleanup_expired_evidence(
    session: Session,
    *,
    report_dir: Path | None = None,
    now: datetime | None = None,
    actor_id: UUID | None = None,
    dry_run: bool = False,
) -> CleanupResult:
    """Delete evidence and artifacts past each project's retention window.

    Intended to be run on a schedule. Safe to run repeatedly: a second pass over
    the same data removes nothing. ``dry_run`` reports the same counts without
    deleting anything or committing.

    Findings and report rows are **not** deleted. A finding is the assessment
    result, and discarding it because its supporting evidence aged out would
    throw away the answer while keeping the metadata. The evidence is the
    sensitive payload and the artifact is the shareable file, so the window
    applies to those.
    """

    reference = now or datetime.now(UTC)
    projects = session.scalars(select(Project)).all()

    evidence_deleted = 0
    reports_expired = 0
    artifacts_deleted = 0
    artifacts_missing = 0

    for project in projects:
        cutoff = project_retention_cutoff(project, now=reference)
        if cutoff is None:
            continue

        stale_evidence = session.scalars(
            select(Evidence)
            .join(Finding, Finding.id == Evidence.finding_id)
            .join(Execution, Execution.id == Finding.execution_id)
            .where(
                Execution.project_id == project.id,
                Evidence.created_at < cutoff,
            )
        ).all()
        evidence_deleted += len(stale_evidence)
        if not dry_run:
            for record in stale_evidence:
                session.delete(record)

        # A report artifact is a file on disk; once the file is gone the row
        # holds no sensitive content.
        stale_reports = session.scalars(
            select(Report).where(
                Report.project_id == project.id,
                Report.created_at < cutoff,
            )
        ).all()
        reports_expired += len(stale_reports)
        for report in stale_reports:
            if report.path:
                artifact = Path(report.path)
                # Only touch files inside the configured report directory, so a
                # malformed path cannot delete something outside it.
                if report_dir is not None and not _within(artifact, report_dir):
                    artifacts_missing += 1
                elif artifact.exists():
                    artifacts_deleted += 1
                    if not dry_run:
                        artifact.unlink(missing_ok=True)
                else:
                    artifacts_missing += 1
            if not dry_run:
                # Keep the row as a record of what was produced; clear the path
                # so a stale download cannot be served and re-generation is
                # unambiguous.
                report.path = ""

    if not dry_run and (evidence_deleted or artifacts_deleted):
        record_audit_event(
            session,
            actor_id=actor_id,
            action="evidence.retention_purged",
            resource_type="retention",
            resource_id=None,
            event_metadata={
                "projects_scanned": len(projects),
                "evidence_deleted": evidence_deleted,
                "reports_expired": reports_expired,
                "artifacts_deleted": artifacts_deleted,
                "artifacts_missing": artifacts_missing,
            },
        )

    if dry_run:
        session.rollback()
    else:
        session.commit()

    return CleanupResult(
        projects_scanned=len(projects),
        evidence_deleted=evidence_deleted,
        reports_expired=reports_expired,
        artifacts_deleted=artifacts_deleted,
        artifacts_missing=artifacts_missing,
    )


def _within(candidate: Path, directory: Path) -> bool:
    """Return whether a path resolves inside a directory."""

    try:
        directory = directory.resolve()
        candidate = candidate.resolve()
    except OSError:
        return False
    return directory == candidate or directory in candidate.parents


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "CleanupResult",
    "cleanup_expired_evidence",
    "project_retention_cutoff",
]

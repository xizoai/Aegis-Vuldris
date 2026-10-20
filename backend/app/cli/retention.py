"""``python -m app.cli.retention`` — purge evidence past its retention window.

Retention only works if something runs it. This is that something: a scheduled
job, a systemd timer, or a Kubernetes CronJob running this module.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import create_session_factory
from app.services.report_generation import DEFAULT_REPORT_DIR
from app.services.retention import cleanup_expired_evidence


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.retention",
        description="Delete evidence and report artifacts past their retention window.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Report artifact directory. Defaults to AEGIS_REPORT_DIR. Files "
        "outside this directory are never deleted.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the result as JSON for a scheduler to consume.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be removed without deleting.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""

    args = _parse_args(argv)
    report_dir = args.report_dir or DEFAULT_REPORT_DIR

    session = create_session_factory()()
    try:
        result = cleanup_expired_evidence(
            session,
            report_dir=report_dir,
            dry_run=args.dry_run,
        )

        payload = {
            "projects_scanned": result.projects_scanned,
            "evidence_deleted": result.evidence_deleted,
            "reports_expired": result.reports_expired,
            "artifacts_deleted": result.artifacts_deleted,
            "artifacts_missing": result.artifacts_missing,
            "report_dir": str(report_dir),
            "dry_run": args.dry_run,
        }

        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"scanned {result.projects_scanned} project(s): "
                f"{result.evidence_deleted} evidence, "
                f"{result.artifacts_deleted} artifact(s) removed, "
                f"{result.artifacts_missing} already missing"
            )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())

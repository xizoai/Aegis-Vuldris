"""``python -m app.cli.clear_history`` — delete past execution data for a project.

Removes executions, execution steps, findings, and evidence. Test definitions
and reports are preserved. Useful for resetting a project between major
re-runs or clearing accumulated logs without dropping the whole project.

Usage:
    python -m app.cli.clear_history --project <uuid> --email owner@example.com

Options:
    --project UUID    Project to clear (required)
    --email EMAIL    Owner account performing the deletion (required)
    --execution UUID  Delete a single execution log instead of all history
    --dry-run        Report what would be deleted without removing anything
    --json           Emit the result as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from app.db.session import create_session_factory
from app.models.execution import Execution
from app.models.execution_step import ExecutionStep
from app.models.finding import Finding
from app.models.project import Project
from app.models.user import User
from app.services.assessments import delete_execution, delete_execution_history


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.clear_history",
        description="Delete past executions, findings, and evidence for a project.",
    )
    parser.add_argument(
        "--project",
        required=True,
        type=UUID,
        help="Project ID to clear.",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email of the user performing the deletion.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without removing anything.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the result as JSON.",
    )
    parser.add_argument(
        "--execution",
        type=UUID,
        default=None,
        help="Delete a single execution log instead of all history.",
    )
    return parser.parse_args(argv)


def _count_cascades(session, execution_ids: Sequence[UUID]) -> int:
    if not execution_ids:
        return 0
    return session.scalar(
        select(func.count())
        .select_from(ExecutionStep)
        .where(ExecutionStep.execution_id.in_(execution_ids))
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    session = create_session_factory()()

    try:
        project = session.get(Project, args.project)
        if project is None:
            print(f"error: project {args.project} not found", file=sys.stderr)
            return 1

        user = session.scalar(select(User).where(User.email == args.email))
        if user is None:
            print(f"error: no user with email {args.email!r}", file=sys.stderr)
            return 1

        if args.execution:
            execution = session.get(Execution, args.execution)
            if execution is None:
                print(f"error: execution {args.execution} not found", file=sys.stderr)
                return 1
            if execution.project_id != project.id:
                print("error: execution does not belong to this project", file=sys.stderr)
                return 1

            steps = _count_cascades(session, [execution.id])
            findings = (
                session.scalar(
                    select(func.count())
                    .select_from(Finding)
                    .where(Finding.execution_id == execution.id)
                )
                or 0
            )

            if args.dry_run:
                result = {
                    "project_id": str(project.id),
                    "execution_id": str(execution.id),
                    "execution_steps": steps,
                    "findings": findings,
                    "dry_run": True,
                }
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    print(
                        f"would delete execution {execution.id} from "
                        f"{project.name!r} ({steps} step(s), {findings} finding(s))"
                    )
                return 0

            delete_execution(session, execution.id, user)
            result = {
                "project_id": str(project.id),
                "execution_id": str(execution.id),
                "deleted": True,
                "executed_at": datetime.utcnow().isoformat() + "Z",
            }
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"deleted execution {execution.id} from {project.name!r}")
            return 0

        execution_ids = list(
            session.scalars(select(Execution.id).where(Execution.project_id == project.id)).all()
        )
        execution_count = len(execution_ids)
        step_count = _count_cascades(session, execution_ids)
        finding_count = (
            session.scalar(
                select(func.count())
                .select_from(Finding)
                .where(Finding.execution_id.in_(execution_ids))
            )
            if execution_ids
            else 0
        )

        if args.dry_run:
            result = {
                "project_id": str(project.id),
                "executions": execution_count,
                "execution_steps": step_count,
                "findings": finding_count,
                "dry_run": True,
            }
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(
                    f"would delete {execution_count} execution(s), "
                    f"{step_count} step(s), and "
                    f"{finding_count} finding(s) from {project.name!r}"
                )
            return 0

        deleted = delete_execution_history(session, project.id, user)

        result = {
            "project_id": str(project.id),
            "executions_deleted": deleted,
            "executed_at": datetime.utcnow().isoformat() + "Z",
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"deleted {deleted} execution(s) from {project.name!r}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())

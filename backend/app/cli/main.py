"""``aegis`` -- the Aegis Vuldris command-line interface.

One entry point for local operations: diagnostics, seeding, running
assessments, exporting reports, and verifying fixed findings. Every
subcommand calls the same service layer the API uses; none of them
contains business logic of its own. That keeps ``aegis run`` honest: a
finding produced from the terminal is the same row the API would have
produced, graded by the same deterministic grader.

Exit-code contract (also documented in docs/Manual.md):

    0  success; no configured failure condition matched
    1  usage or configuration error (bad arguments, unknown ids, missing
       account, a verification requested for a finding that is not fixed)
    2  a configured condition matched (--fail-on threshold, --baseline
       regression, --fail-on-inconclusive)
    4  operational error (database unavailable, target unreachable, the
       execution engine failed)

A CI job can therefore distinguish "the scanner found what you told it to
care about" (2) from "the scanner itself broke" (4). argparse's own usage
errors exit 1, never 2, so a typo can never be read as a finding.

The ``seed-tests``, ``retention prune``, ``clear-history``,
``grading-accuracy`` and ``judge-calibration`` subcommands forward to the
existing ``python -m app.cli.*`` modules unchanged; their own ``--help``
still works.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import sys
import textwrap
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.errors import (
    AssessmentNotFoundError,
    ExecutionBindingError,
    PermissionDeniedError,
    ProjectNotFoundError,
    TargetNotFoundError,
)
from app.cli import clear_history as clear_history_cli
from app.cli import demo as demo_cli
from app.cli import grading_accuracy as grading_accuracy_cli
from app.cli import judge_calibration as judge_calibration_cli
from app.cli import retention as retention_cli
from app.cli import seed_tests as seed_tests_cli
from app.core.config import get_settings
from app.db.session import create_session_factory
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.finding import Finding, FindingConfirmation, FindingSeverity
from app.models.project import Project
from app.models.report import Report
from app.models.target import Target, TargetStatus
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas import ExecutionCreate, ReportCreate, VerificationCreate
from app.schemas.test_case import TestCaseCategory
from app.security.network import NetworkPolicyError, validate_target_endpoint
from app.services.assessments import (
    create_execution,
    create_report,
    validate_execution_binding,
)
from app.services.audit import record_audit_event
from app.services.demo import DEMO_MARKER
from app.services.execution_engine import ExecutionEngine
from app.services.extensions import (
    discover_adapter_factories,
    discover_attack_plugin_dirs,
    discover_graders,
    discover_report_exporters,
    summary_line,
)
from app.services.regression import (
    diff_findings,
    evaluate_regression_gate,
    load_baseline_file,
    regressions_at_or_above,
)
from app.services.report_generation import (
    compare_reports,
    generate_report,
    require_project_report,
)
from app.services.risk_scoring import severity_to_score
from app.services.verification import create_verification_execution

__all__ = ["main"]

_SEVERITY_CHOICES = [severity.value for severity in FindingSeverity]
_SUITE_CHOICES = [category.value for category in TestCaseCategory]


class _UsageError(Exception):
    """A configuration or usage problem that maps to exit code 1."""


class _UsageParser(argparse.ArgumentParser):
    """Parser whose usage errors exit 1, matching the CLI contract.

    argparse's default code for a usage error is 2, which this CLI reserves
    for "a configured condition matched" (for example ``--fail-on``). A CI
    job must never read a typo as a security finding.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _package_version() -> str | None:
    """Return the installed aegis-vuldris version, or None for a source checkout."""

    try:
        return distribution_version("aegis-vuldris")
    except PackageNotFoundError:
        return None


def _version_text() -> str:
    return _package_version() or "source checkout (not installed)"


def _first_line(exc: BaseException) -> str:
    message = str(exc).strip()
    return message.splitlines()[0] if message else type(exc).__name__


def _open_session() -> Session:
    return create_session_factory()()


def _default_engine() -> ExecutionEngine:
    """Build the engine used by ``run`` and ``verify``.

    A separate function (rather than an inline call) so tests can substitute
    an engine with a deterministic adapter factory.
    """

    return ExecutionEngine()


def _require_user(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        raise _UsageError(f"no account with email {email!r}")
    return user


def _test_category(test: SecurityTest) -> str:
    config = test.config or {}
    return str(config.get("category", "unknown"))


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def _find_alembic_ini() -> Path | None:
    """Locate alembic.ini next to the checkout or in the working directory.

    A wheel install ships the application but not the migration scripts, so
    "not found" is a normal answer, not an error.
    """

    candidates = (
        Path(__file__).resolve().parents[3] / "alembic.ini",
        Path.cwd() / "alembic.ini",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _check_migrations(session: Session) -> tuple[int, str] | None:
    """Print migration state; return a problem tuple when out of sync."""

    ini = _find_alembic_ini()
    if ini is None:
        print("migrations: skipped (alembic.ini not found; no migration scripts in this install)")
        return None

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    config = Config(str(ini))
    head = ScriptDirectory.from_config(config).get_current_head()
    current = MigrationContext.configure(session.connection()).get_current_revision()
    if current == head:
        print(f"migrations: current {current or 'base'}, head {head or 'base'}, match")
        return None
    print(f"migrations: current {current or 'none'}, head {head or 'none'}, MISMATCH")
    return (1, "database schema is not at the migration head; run 'alembic upgrade head'")


def _print_targets(session: Session) -> None:
    targets = list(
        session.scalars(
            select(Target).where(Target.status == TargetStatus.ACTIVE).order_by(Target.name)
        ).all()
    )
    print(f"targets: {len(targets)} active")
    for target in targets:
        try:
            validate_target_endpoint(target.endpoint)
            policy = "ok"
        except NetworkPolicyError as exc:
            policy = f"blocked ({exc})"
        print(f"  - {target.name} [{target.provider.value}] {target.endpoint} -> policy: {policy}")


def _database_encoding_problem(server_encoding: str | None) -> tuple[int, str] | None:
    """Flag a PostgreSQL server encoding that is not UTF8.

    JSONB payloads — test configs, model replies, evidence — can contain any
    Unicode. On a non-UTF8 database those writes are silently transcoded into
    bytes the read path cannot decode, so the failure surfaces later as a
    ``UnicodeDecodeError`` in an unrelated command. Encoding is fixed when the
    database is created, so the only fix is to recreate it.
    """

    if server_encoding is None or server_encoding.upper() == "UTF8":
        return None
    return (
        1,
        f"database encoding is {server_encoding}, not UTF8; non-ASCII payloads "
        "will be corrupted. Recreate the database with ENCODING 'UTF8' "
        "(see docs/troubleshooting.md#database-encoding)",
    )


def _cmd_doctor(*, session_factory: Callable[[], Session] | None = None) -> int:
    problems: list[tuple[int, str]] = []
    settings = get_settings()

    print("aegis doctor")
    print(f"aegis: {_version_text()}")
    print(f"python: {platform.python_version()} ({platform.system()} {platform.release()})")
    print(f"app_env: {settings.app_env}")

    if settings.secret_key:
        print("secret_key: present")
    else:
        print("secret_key: missing")
        if settings.app_env in ("staging", "production"):
            problems.append((1, f"SECRET_KEY is required when APP_ENV={settings.app_env}"))

    session = (session_factory or _open_session)()
    try:
        session.execute(text("SELECT 1"))
        dialect = session.get_bind().dialect.name
        print(f"database: ok ({dialect})")
        if dialect == "postgresql":
            server_encoding = session.execute(text("SHOW server_encoding")).scalar()
            if server_encoding:
                print(f"database encoding: {server_encoding}")
            encoding_problem = _database_encoding_problem(server_encoding)
            if encoding_problem is not None:
                problems.append(encoding_problem)
        migration_problem = _check_migrations(session)
        if migration_problem is not None:
            problems.append(migration_problem)
        _print_targets(session)
        demo_count = len(
            list(session.scalars(select(Project).where(Project.name.startswith(DEMO_MARKER))).all())
        )
        if demo_count:
            print(f"demo: {demo_count} synthetic project(s) seeded")
        else:
            print("demo: none seeded (run 'aegis demo' to create one)")
        print(
            summary_line(
                [
                    discover_graders(),
                    discover_report_exporters(),
                    discover_attack_plugin_dirs(),
                    discover_adapter_factories(),
                ]
            )
        )
    except SQLAlchemyError as exc:
        problems.append((4, f"database unreachable: {_first_line(exc)}"))
        print(f"database: unreachable: {_first_line(exc)}")
    finally:
        session.close()

    for _, message in problems:
        print(f"problem: {message}")
    if problems:
        return 4 if any(code == 4 for code, _ in problems) else 1
    print("result: ok")
    return 0


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


def _select_tests(
    session: Session, project_id: UUID, suites: list[str] | None
) -> list[SecurityTest]:
    tests = list(
        session.scalars(
            select(SecurityTest)
            .where(SecurityTest.project_id == project_id)
            .order_by(SecurityTest.created_at, SecurityTest.id)
        ).all()
    )
    if suites:
        wanted = set(suites)
        tests = [test for test in tests if _test_category(test) in wanted]
    return tests


def _load_run_record(session: Session, test: SecurityTest, execution: Execution) -> dict[str, Any]:
    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.execution_id == execution.id)
            .order_by(Finding.created_at, Finding.id)
        ).all()
    )
    highest = max((finding.severity for finding in findings), key=severity_to_score, default=None)
    category = _test_category(test)
    return {
        "test_id": str(test.id),
        "test_name": test.name,
        "category": category,
        "test_category": category,
        "execution_id": str(execution.id),
        "status": execution.status.value,
        "result": execution.result.value if execution.result else None,
        "error": execution.error,
        "severity": highest.value if highest else None,
        "findings": [
            {
                "id": str(finding.id),
                "title": finding.title,
                "severity": finding.severity.value,
                "status": finding.status.value,
                # Two-stage grading: a candidate match is reported but is not
                # a confirmed attack, and a dismissed one is a reviewer's
                # false-positive call.
                "confirmation": finding.confirmation.value,
                "test_category": category,
            }
            for finding in findings
        ],
    }


def _baseline_payload(diff: dict[str, Any], regressions: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "new_count": diff["new_count"],
        "resolved_count": diff["resolved_count"],
        "regressed_count": diff["regressed_count"],
        "improved_count": diff["improved_count"],
        "unchanged_count": diff["unchanged_count"],
        "regressions": regressions,
    }


def _baseline_from_report(
    session: Session,
    project_id: UUID,
    baseline_id: UUID,
    fail_on: str | None,
    user: User,
) -> tuple[dict[str, Any], list[str]]:
    """Compare the project's current state against a generated baseline report.

    A fresh JSON report is generated for the current state and compared with
    the baseline snapshot through the same ``compare_reports`` the API uses.
    """

    require_project_report(session, user, project_id, baseline_id)
    report = create_report(
        session,
        project_id,
        ReportCreate(title=f"aegis run {datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC", format="json"),
        user,
    )
    generate_report(session, report)
    record_audit_event(
        session,
        actor_id=user.id,
        action="report.generated",
        resource_type="report",
        resource_id=str(report.id),
        event_metadata={"project_id": str(project_id), "format": report.format},
    )
    try:
        comparison = compare_reports(session, baseline_id, report.id, project_id)
    except FileNotFoundError as exc:
        raise _UsageError(f"baseline report {baseline_id} cannot be compared: {exc}") from None

    verdict = evaluate_regression_gate(comparison, fail_on=fail_on)
    payload = _baseline_payload(comparison, regressions_at_or_above(comparison, fail_on))
    payload.update(
        {"form": "report", "baseline_report_id": str(baseline_id), "report_id": str(report.id)}
    )
    return payload, verdict.reasons


def _baseline_from_file(
    baseline_ref: str,
    fail_on: str | None,
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Compare this run's findings against a saved JSON report artifact.

    The file form needs no database reports: a CI job can commit the artifact
    from the last good run and gate every later run against it.
    """

    try:
        baseline_findings = load_baseline_file(Path(baseline_ref))
    except OSError as exc:
        raise _UsageError(f"baseline file {baseline_ref} cannot be read: {exc}") from None
    except ValueError as exc:
        raise _UsageError(str(exc)) from None

    current_findings = [finding for record in records for finding in record["findings"]]
    diff = diff_findings(baseline_findings, current_findings)
    verdict = evaluate_regression_gate(diff, fail_on=fail_on)
    payload = _baseline_payload(diff, regressions_at_or_above(diff, fail_on))
    payload.update({"form": "file", "baseline": baseline_ref})
    return payload, verdict.reasons


def _evaluate_baseline(
    session: Session,
    project_id: UUID,
    baseline_ref: str,
    fail_on: str | None,
    user: User,
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    try:
        baseline_id = UUID(baseline_ref)
    except ValueError:
        return _baseline_from_file(baseline_ref, fail_on, records)
    return _baseline_from_report(session, project_id, baseline_id, fail_on, user)


def _cmd_run(
    args: argparse.Namespace,
    *,
    session_factory: Callable[[], Session] | None = None,
    engine_factory: Callable[[], ExecutionEngine] | None = None,
) -> int:
    session = (session_factory or _open_session)()
    try:
        user = _require_user(session, args.email)
        project = session.get(Project, args.project)
        if project is None:
            raise _UsageError(f"project {args.project} does not exist")
        target = session.get(Target, args.target)
        if target is None or target.project_id != project.id:
            raise _UsageError(f"target {args.target} does not exist in project {args.project}")

        selected = _select_tests(session, project.id, args.suite)
        if not selected:
            raise _UsageError(
                "no security tests matched; seed the attack library first "
                "(see 'aegis seed-tests --help')"
            )

        runnable: list[SecurityTest] = []
        skipped: list[dict[str, str]] = []
        for test in selected:
            try:
                validate_execution_binding(test, target)
            except ExecutionBindingError as exc:
                skipped.append(
                    {"test_id": str(test.id), "test_name": test.name, "reason": str(exc)}
                )
            else:
                runnable.append(test)
        if not runnable:
            raise _UsageError(
                f"every selected test is blocked by the target: {skipped[0]['reason']}"
            )

        engine = (engine_factory or _default_engine)()
        records: list[dict[str, Any]] = []
        for test in runnable:
            execution = create_execution(
                session,
                project.id,
                ExecutionCreate(test_id=test.id, target_id=target.id),
                user,
            )
            asyncio.run(engine.run_single(execution.id))
            session.refresh(execution)
            records.append(_load_run_record(session, test, execution))

        operational = [
            record for record in records if record["status"] != ExecutionStatus.SUCCEEDED.value
        ]
        reasons: list[str] = []
        baseline_payload: dict[str, Any] | None = None
        if operational:
            reasons.extend(
                f"operational: {record['test_name']}: {record['error'] or record['status']}"
                for record in operational
            )
        else:
            if args.fail_on is not None:
                threshold = severity_to_score(FindingSeverity(args.fail_on))
                for record in records:
                    for finding in record["findings"]:
                        if finding["confirmation"] == FindingConfirmation.DISMISSED.value:
                            # A reviewer has already ruled this a false
                            # positive; it must not gate a build.
                            continue
                        if severity_to_score(FindingSeverity(finding["severity"])) >= threshold:
                            unconfirmed = (
                                " (unconfirmed candidate)"
                                if finding["confirmation"] == FindingConfirmation.CANDIDATE.value
                                else ""
                            )
                            reasons.append(
                                f"threshold: {finding['severity']} finding '{finding['title']}' "
                                f"in {record['test_name']} is at or above --fail-on {args.fail_on}"
                                f"{unconfirmed}"
                            )
            inconclusive = [
                record
                for record in records
                if record["result"] == ExecutionResult.INCONCLUSIVE.value
            ]
            if args.fail_on_inconclusive and inconclusive:
                reasons.extend(f"inconclusive: {record['test_name']}" for record in inconclusive)
            if args.baseline is not None:
                baseline_payload, baseline_reasons = _evaluate_baseline(
                    session, project.id, args.baseline, args.fail_on, user, records
                )
                reasons.extend(baseline_reasons)

        exit_code = 4 if operational else (2 if reasons else 0)
        payload = {
            "project_id": str(project.id),
            "project": project.name,
            "target_id": str(target.id),
            "target": target.name,
            "suites": args.suite or [],
            "fail_on": args.fail_on,
            "fail_on_inconclusive": bool(args.fail_on_inconclusive),
            "baseline": baseline_payload,
            "executions": records,
            "skipped": skipped,
            "totals": {
                "selected": len(selected),
                "run": len(records),
                "succeeded": sum(
                    1 for r in records if r["status"] == ExecutionStatus.SUCCEEDED.value
                ),
                "failed": len(operational),
                "inconclusive": sum(
                    1 for r in records if r["result"] == ExecutionResult.INCONCLUSIVE.value
                ),
                "needs_review": sum(
                    1 for r in records if r["result"] == ExecutionResult.NEEDS_REVIEW.value
                ),
                "findings": sum(len(r["findings"]) for r in records),
            },
            "reasons": reasons,
            "exit_code": exit_code,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            _print_run_summary(records, skipped, reasons, exit_code)
        return exit_code
    finally:
        session.close()


def _print_run_summary(
    records: list[dict[str, Any]],
    skipped: list[dict[str, str]],
    reasons: list[str],
    exit_code: int,
) -> None:
    for record in records:
        if record["status"] != ExecutionStatus.SUCCEEDED.value:
            label = record["status"].replace("_", " ").upper()
        else:
            label = str(record["result"] or record["status"]).replace("_", " ").upper()
        count = len(record["findings"])
        suffix = f" - {count} finding{'s' if count != 1 else ''}" if count else ""
        highest = f" (highest: {record['severity']})" if record["severity"] else ""
        print(f"  [{label}] {record['test_name']}{suffix}{highest}")
    for entry in skipped:
        print(f"  [SKIPPED] {entry['test_name']} - {entry['reason']}")
    print(f"totals: {len(records)} run, {len(skipped)} skipped")
    for reason in reasons:
        print(f"reason: {reason}")
    print(f"exit code: {exit_code}")


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------


def _cmd_verify(
    args: argparse.Namespace,
    *,
    session_factory: Callable[[], Session] | None = None,
    engine_factory: Callable[[], ExecutionEngine] | None = None,
) -> int:
    session = (session_factory or _open_session)()
    try:
        user = _require_user(session, args.email)
        finding = session.get(Finding, args.finding_id)
        if finding is None:
            raise _UsageError(f"finding {args.finding_id} does not exist")
        source = session.get(Execution, finding.execution_id)
        if source is None:
            raise _UsageError(f"finding {finding.id} has no source execution")

        execution = create_verification_execution(
            session,
            source.project_id,
            finding.id,
            VerificationCreate(target_id=args.target),
            user,
        )
        print(f"finding: {finding.title}")
        print(f"verification execution: {execution.id}")

        engine = (engine_factory or _default_engine)()
        asyncio.run(engine.run_single(execution.id))

        session.expire_all()
        execution = session.get(Execution, execution.id)
        finding = session.get(Finding, finding.id)
        if execution is None or finding is None:  # pragma: no cover - defensive
            raise _UsageError("the verification result disappeared; re-run the command")

        if execution.status != ExecutionStatus.SUCCEEDED:
            print(
                f"result: rerun did not complete ({execution.status.value}): "
                f"{execution.error or 'unknown error'}"
            )
            return 4

        print(f"rerun result: {execution.result.value if execution.result else 'none'}")
        print(f"fix state: {finding.status.value}")
        if execution.result in (ExecutionResult.PASS, ExecutionResult.NO_FINDINGS):
            return 0
        if execution.result in (ExecutionResult.FAIL, ExecutionResult.NEEDS_REVIEW):
            # ``needs_review`` means the rerun still matched the attack's
            # patterns and nothing confirmed or dismissed the match. A fix is
            # verified only by a clean pass, so an unresolved rerun fails the
            # check instead of silently reading as "not reproduced".
            return 2
        return 2 if args.fail_on_inconclusive else 0
    finally:
        session.close()


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def _cmd_export(
    args: argparse.Namespace,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    session = (session_factory or _open_session)()
    try:
        user = _require_user(session, args.email)
        report = session.get(Report, args.report)
        if report is None:
            raise _UsageError(f"report {args.report} does not exist")
        project_id = report.project_id
        require_project_report(session, user, project_id, report.id)

        if args.format is not None and report.format != args.format:
            report.format = args.format
            session.commit()
        baseline_report_id = None
        if args.baseline is not None:
            # The baseline is read during generation; authorize it exactly
            # like the report being exported.
            require_project_report(session, user, project_id, args.baseline)
            baseline_report_id = args.baseline
        artifact = generate_report(session, report, baseline_report_id=baseline_report_id)
        record_audit_event(
            session,
            actor_id=user.id,
            action="report.generated",
            resource_type="report",
            resource_id=str(report.id),
            event_metadata={"project_id": str(project_id), "format": report.format},
        )

        output = Path(artifact)
        if args.output is not None:
            output = args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact, output)
            record_audit_event(
                session,
                actor_id=user.id,
                action="report.downloaded",
                resource_type="report",
                resource_id=str(report.id),
                event_metadata={"project_id": str(project_id)},
            )
        print(f"report: {report.id}")
        print(f"format: {report.format}")
        print(f"artifact: {output}")
        return 0
    finally:
        session.close()


# --------------------------------------------------------------------------
# parser and dispatch
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    epilog = textwrap.dedent(
        """\
        exit codes:
          0  success; no configured failure condition matched
          1  usage or configuration error
          2  a configured condition matched (--fail-on, --baseline, --fail-on-inconclusive)
          4  operational error (database, network, engine)
        """
    )
    parser = _UsageParser(
        prog="aegis",
        description=(
            "Run Aegis Vuldris assessments from the command line. Every subcommand calls "
            "the same service layer as the API."
        ),
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"aegis {_version_text()}")
    subparsers = parser.add_subparsers(dest="command", metavar="command", required=True)

    subparsers.add_parser(
        "doctor",
        help="Diagnose environment, database, migrations, secret key, and targets.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run a project's tests against one target through the shared engine.",
    )
    run_parser.add_argument(
        "--project", type=UUID, required=True, metavar="UUID", help="Project id."
    )
    run_parser.add_argument(
        "--target", type=UUID, required=True, metavar="UUID", help="Target id in the same project."
    )
    run_parser.add_argument(
        "--email", required=True, help="Account performing the run (needs project write access)."
    )
    run_parser.add_argument(
        "--suite",
        action="append",
        choices=_SUITE_CHOICES,
        metavar="CATEGORY",
        help="Limit to a test category; repeatable. Default: every test in the project.",
    )
    run_parser.add_argument(
        "--fail-on",
        choices=_SEVERITY_CHOICES,
        metavar="SEVERITY",
        help="Exit 2 when any finding from this run is at or above SEVERITY.",
    )
    run_parser.add_argument(
        "--baseline",
        metavar="REPORT_ID_OR_FILE",
        help=(
            "Exit 2 on findings that are new or regressed versus a baseline: either a "
            "generated report id in the same project, or the path to a saved JSON "
            "report artifact (severity-filtered when --fail-on is also given)."
        ),
    )
    run_parser.add_argument(
        "--fail-on-inconclusive",
        action="store_true",
        help="Exit 2 when any run is inconclusive.",
    )
    run_parser.add_argument(
        "--json", action="store_true", help="Print a machine-readable summary to stdout."
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help=(
            "Re-run the exact attack behind a finding and report the verdict; "
            "exit 2 means it still reproduces."
        ),
    )
    verify_parser.add_argument("finding_id", type=UUID, metavar="FINDING_ID")
    verify_parser.add_argument(
        "--email", required=True, help="Account performing the verification (needs write access)."
    )
    verify_parser.add_argument(
        "--target",
        type=UUID,
        metavar="UUID",
        help="Verify against this target instead of the original one.",
    )
    verify_parser.add_argument(
        "--fail-on-inconclusive",
        action="store_true",
        help="Exit 2 when the rerun is inconclusive.",
    )

    export_parser = subparsers.add_parser(
        "export",
        help="Generate a report artifact and print its path (or copy it with --output).",
    )
    export_parser.add_argument(
        "--report", type=UUID, required=True, metavar="REPORT_ID", help="Report id."
    )
    export_parser.add_argument(
        "--email", required=True, help="Account performing the export (needs project access)."
    )
    export_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        help="Regenerate in this format. Default: the report's stored format.",
    )
    export_parser.add_argument(
        "--baseline",
        type=UUID,
        metavar="REPORT_ID",
        help="Embed a 'changes since baseline' section comparing against this generated report.",
    )
    export_parser.add_argument(
        "--output", type=Path, metavar="PATH", help="Also copy the artifact to PATH."
    )

    subparsers.add_parser(
        "demo",
        add_help=False,
        help="Seed an offline synthetic demo project (see: aegis demo --help).",
    )
    subparsers.add_parser(
        "seed-tests",
        add_help=False,
        help="Import the bundled attack library (see: aegis seed-tests --help).",
    )
    subparsers.add_parser(
        "retention",
        add_help=False,
        help="Prune evidence past its retention window (see: aegis retention prune --help).",
    )
    subparsers.add_parser(
        "clear-history",
        add_help=False,
        help="Delete a project's execution history (see: aegis clear-history --help).",
    )
    subparsers.add_parser(
        "grading-accuracy",
        add_help=False,
        help=(
            "Measure the grader's false-positive rate against known-safe "
            "responses (see: aegis grading-accuracy --help)."
        ),
    )
    subparsers.add_parser(
        "judge-calibration",
        add_help=False,
        help=(
            "Measure the confirmation judge against labeled transcripts "
            "(see: aegis judge-calibration --help)."
        ),
    )
    return parser


def _dispatch(argv: Sequence[str] | None) -> int:
    parser = _build_parser()
    args, forwarded = parser.parse_known_args(argv)

    # The wrapper commands own their argument parsing; their remaining tokens
    # arrive here untouched and are forwarded verbatim.
    if args.command == "seed-tests":
        return seed_tests_cli.main(forwarded)
    if args.command == "demo":
        return demo_cli.main(forwarded)
    if args.command == "clear-history":
        return clear_history_cli.main(forwarded)
    if args.command == "retention":
        if not forwarded or forwarded[0] != "prune":
            raise _UsageError("usage: aegis retention prune [options]")
        return retention_cli.main(forwarded[1:])
    if args.command == "grading-accuracy":
        return grading_accuracy_cli.main(forwarded)
    if args.command == "judge-calibration":
        return judge_calibration_cli.main(forwarded)

    if forwarded:
        parser.error(f"unrecognized arguments: {' '.join(forwarded)}")

    if args.command == "doctor":
        return _cmd_doctor()
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "export":
        return _cmd_export(args)
    raise _UsageError(f"unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _dispatch(argv)
    except SystemExit as exc:
        # argparse exits directly for --help/--version and for usage errors.
        # Usage errors default to 2; remap to the documented 1.
        code = exc.code
        if code is None or code == 0:
            return 0
        if code == 2:
            return 1
        return code if isinstance(code, int) else 1
    except _UsageError as exc:
        print(f"aegis: error: {exc}", file=sys.stderr)
        return 1
    except (
        ProjectNotFoundError,
        TargetNotFoundError,
        AssessmentNotFoundError,
        ExecutionBindingError,
        PermissionDeniedError,
    ) as exc:
        print(f"aegis: error: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print(f"aegis: configuration error: {_first_line(exc)}", file=sys.stderr)
        return 1
    except (SQLAlchemyError, OSError) as exc:
        print(f"aegis: operational error: {_first_line(exc)}", file=sys.stderr)
        return 4
    except Exception as exc:  # noqa: BLE001 - the CLI contract requires exit 4, not a traceback
        if os.environ.get("AEGIS_CLI_TRACEBACK"):
            raise
        print(f"aegis: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("aegis: run 'aegis doctor' for diagnostics", file=sys.stderr)
        return 4


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""``python -m app.cli.judge_calibration`` — calibrate the confirmation judge.

The precision gate (``grading-accuracy``) proves the grader does not cry wolf.
This command proves the opposite side: of transcripts whose ground truth is
known, how many does the confirmation judge get right, and in which direction
does it err? It runs the same confirmation prompt and verdict parser the
execution engine uses, so the numbers describe the deployed pipeline, not a
parallel implementation.

Three modes, in order of increasing setup:

- **bundled corpus, no judge** — stage-one (lexical) recall only; offline.
- **replay** (``--judge-outputs FILE``) — re-evaluates recorded judge outputs;
  fully reproducible without a model, which is how a published agreement
  number is re-checked.
- **live** (``--judge-target UUID --email EMAIL``) — calls the judge through
  the real adapter stack and the target's stored credential; ``--record FILE``
  saves the raw outputs so the run can be replayed later.

Exit codes:

    0  measured; no configured threshold was breached
    1  usage or configuration error (bad files, bad thresholds, no judge)
    2  a configured threshold was breached (--min-detector-recall,
       --min-judge-accuracy, --min-judge-recall)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import BaseTargetAdapter
from app.adapters.registry import create_model_adapter
from app.api.errors import PermissionDeniedError
from app.db.session import create_session_factory
from app.models.model import ModelMessage, ModelRequest
from app.models.project import Project
from app.models.target import Target, TargetStatus
from app.models.user import User
from app.security.secrets import SecretStore, get_secret_store
from app.services.calibration_corpus import BUNDLED_ITEMS, CalibrationItem
from app.services.judge_calibration import (
    CalibrationReport,
    JudgeCallable,
    load_items_file,
    load_recorded_outputs,
    run_calibration,
    write_recorded_outputs,
)
from app.services.projects import ensure_project_access


class _CalibrationUsageError(Exception):
    """A configuration problem that maps to exit code 1."""


SessionFactory = Callable[[], Session]
AdapterFactory = Callable[..., BaseTargetAdapter]


def _default_session() -> Session:
    """Open a session from the application's configured factory."""

    return create_session_factory()()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aegis judge-calibration",
        description=(
            "Measure the confirmation judge against labeled transcripts: "
            "agreement, precision/recall, and stage-one recall."
        ),
    )
    parser.add_argument(
        "--items",
        type=Path,
        action="append",
        metavar="PATH",
        help=(
            "Labeled items to calibrate with (.jsonl, .json, or .csv; "
            "repeatable). Default: the bundled calibration corpus."
        ),
    )
    parser.add_argument(
        "--judge-target",
        type=UUID,
        metavar="UUID",
        help=(
            "Target whose model acts as the confirmation judge. Requires "
            "--email; uses the target's stored credential and endpoint."
        ),
    )
    parser.add_argument(
        "--email",
        help="Account performing the calibration (needs project write access).",
    )
    parser.add_argument(
        "--judge-model",
        metavar="MODEL",
        help="Pin a different model on the judge endpoint. Default: the target's model.",
    )
    parser.add_argument(
        "--judge-outputs",
        type=Path,
        metavar="PATH",
        help="Replay raw judge outputs recorded by an earlier --record run.",
    )
    parser.add_argument(
        "--record",
        type=Path,
        metavar="PATH",
        help="After a live run, write the raw judge outputs to PATH for replay.",
    )
    parser.add_argument(
        "--min-detector-recall",
        type=float,
        metavar="FRACTION",
        help="Exit 2 when stage-one recall over exploited items is below this fraction.",
    )
    parser.add_argument(
        "--min-judge-accuracy",
        type=float,
        metavar="FRACTION",
        help="Exit 2 when judge agreement over decided items is below this fraction.",
    )
    parser.add_argument(
        "--min-judge-recall",
        type=float,
        metavar="FRACTION",
        help="Exit 2 when the share of exploited items the judge catches is below this fraction.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON for a CI job to consume.",
    )
    return parser.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> str | None:
    for flag in ("min_detector_recall", "min_judge_accuracy", "min_judge_recall"):
        value = getattr(args, flag)
        if value is not None and not 0.0 <= value <= 1.0:
            return f"--{flag.replace('_', '-')} must be a fraction between 0 and 1"
    if args.judge_target is not None and args.judge_outputs is not None:
        return "--judge-target and --judge-outputs are mutually exclusive"
    if args.judge_target is not None and not args.email:
        return "--judge-target requires --email"
    if args.email and args.judge_target is None:
        return "--email is only used with --judge-target"
    if args.judge_model and args.judge_target is None:
        return "--judge-model requires --judge-target"
    if args.record is not None and args.judge_target is None:
        return "--record requires --judge-target; a replay has nothing new to record"
    if (
        (args.min_judge_accuracy is not None or args.min_judge_recall is not None)
        and args.judge_target is None
        and args.judge_outputs is None
    ):
        return (
            "--min-judge-accuracy and --min-judge-recall need a judge: "
            "pass --judge-target with --email, or --judge-outputs"
        )
    return None


def _load_items(paths: list[Path] | None) -> list[CalibrationItem]:
    if not paths:
        return list(BUNDLED_ITEMS)
    items: list[CalibrationItem] = []
    for path in paths:
        items.extend(load_items_file(path))
    return items


def _replay_judge(outputs: dict[str, str | None]) -> JudgeCallable:
    async def judge(item: CalibrationItem, prompt: str) -> str | None:
        if item.name not in outputs:
            raise ValueError(f"no recorded output for item {item.name!r}")
        return outputs[item.name]

    return judge


def _build_adapter(
    target: Target,
    session: Session,
    store: SecretStore,
    adapter_factory: AdapterFactory | None,
) -> BaseTargetAdapter:
    """Build the judge adapter through the same policy path the engine uses."""

    from app.adapters.resolver import create_credential_resolver

    credential_resolver = create_credential_resolver(session, store)
    if adapter_factory is not None:
        return adapter_factory(target.provider, credential_resolver=credential_resolver)
    return create_model_adapter(target.provider, credential_resolver=credential_resolver)


async def _run_live(
    args: argparse.Namespace,
    items: list[CalibrationItem],
    session_factory: SessionFactory | None,
    adapter_factory: AdapterFactory | None,
) -> tuple[CalibrationReport, str]:
    session = (session_factory or _default_session)()
    adapter: BaseTargetAdapter | None = None
    try:
        user = session.scalar(select(User).where(User.email == args.email))
        if user is None:
            raise _CalibrationUsageError(f"no account with email {args.email!r}")
        target = session.get(Target, args.judge_target)
        if target is None:
            raise _CalibrationUsageError(f"judge target {args.judge_target} does not exist")
        if target.status != TargetStatus.ACTIVE:
            raise _CalibrationUsageError(
                "the judge target is inactive; reactivate it before calibrating"
            )
        project = session.get(Project, target.project_id)
        if project is None:  # pragma: no cover - defensive
            raise _CalibrationUsageError("the judge target's project no longer exists")
        ensure_project_access(session, user, project, "update")

        model = args.judge_model or target.model
        if not model:
            raise _CalibrationUsageError(
                "the judge target has no model; set one on the target or pass --judge-model"
            )

        built = _build_adapter(target, session, get_secret_store(), adapter_factory)
        adapter = built

        async def judge(item: CalibrationItem, prompt: str) -> str | None:
            request = ModelRequest(
                messages=[ModelMessage(role="user", content=prompt)],
                model=model,
            )
            response = await asyncio.wait_for(
                built.generate(target, request), timeout=target.timeout_seconds
            )
            return response.output

        return await run_calibration(items, judge=judge), model
    finally:
        if adapter is not None:
            await adapter.close()
        session.close()


def _evaluate_thresholds(
    args: argparse.Namespace, report: CalibrationReport
) -> tuple[list[str], list[str]]:
    """Return (breached-threshold reasons, unavailable-metric problems)."""

    reasons: list[str] = []
    problems: list[str] = []
    if args.min_detector_recall is not None:
        recall = report.detector_recall
        if recall is None:
            problems.append(
                "detector recall is unavailable: no exploited item in the corpus "
                "carries grading rules"
            )
        elif recall < args.min_detector_recall:
            reasons.append(
                f"detector recall {recall:.1%} is below "
                f"--min-detector-recall {args.min_detector_recall:g}"
            )
    if args.min_judge_accuracy is not None:
        accuracy = report.judge_accuracy
        if accuracy is None:
            problems.append("judge accuracy is unavailable: the judge decided no items")
        elif accuracy < args.min_judge_accuracy:
            reasons.append(
                f"judge accuracy {accuracy:.1%} is below "
                f"--min-judge-accuracy {args.min_judge_accuracy:g}"
            )
    if args.min_judge_recall is not None:
        recall = report.judge_exploited_recall
        if recall is None:
            problems.append("judge recall is unavailable: the corpus has no exploited items")
        elif recall < args.min_judge_recall:
            reasons.append(
                f"judge exploited recall {recall:.1%} is below "
                f"--min-judge-recall {args.min_judge_recall:g}"
            )
    return reasons, problems


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _threshold_lines(args: argparse.Namespace, report: CalibrationReport) -> list[str]:
    lines: list[str] = []
    checks: list[tuple[str, float | None, float | None]] = [
        ("--min-detector-recall", args.min_detector_recall, report.detector_recall),
        ("--min-judge-accuracy", args.min_judge_accuracy, report.judge_accuracy),
        ("--min-judge-recall", args.min_judge_recall, report.judge_exploited_recall),
    ]
    for name, threshold, value in checks:
        if threshold is None:
            continue
        verdict = "ok" if value is not None and value >= threshold else "EXCEEDED"
        lines.append(f"threshold: {name} {threshold:g} - {verdict}")
    return lines


def _print_report(
    report: CalibrationReport,
    args: argparse.Namespace,
    reasons: list[str],
    exit_code: int,
    judge_config: dict[str, str] | None,
) -> None:
    print(f"judge calibration: {report.summary()}")

    if report.detector_evaluated:
        print(
            f"detector: {report.detector_caught}/{report.detector_exploited_configured} "
            f"exploited items flagged (recall {_pct(report.detector_recall)})"
        )
        for name in report.detector_missed:
            print(f"  [MISS] {name}: not flagged by the lexical stage")
        for name in report.detector_flagged_refusals:
            print(f"  [CANDIDATE] {name}: flagged; the judge stage must dismiss it")
    else:
        print("detector: no grading rules on these items; stage-one metrics unavailable")

    if judge_config is not None:
        print(f"judge config: target {judge_config['target_id']}, model {judge_config['model']}")

    if report.judge_ran:
        print(
            f"judge: {report.judge_decided}/{report.items_total} decided; "
            f"accuracy {_pct(report.judge_accuracy)} (over decided), "
            f"exploited precision {_pct(report.judge_exploited_precision)}, "
            f"exploited recall {_pct(report.judge_exploited_recall)}, "
            f"refusal recall {_pct(report.judge_refusal_recall)}, "
            f"kappa {_num(report.judge_cohens_kappa)}"
        )
        for mismatch in report.mismatches():
            print(
                f"  [MISS] {mismatch['name']}: expected {mismatch['expected']}, "
                f"judge said {mismatch['verdict']}"
            )
        for abstained in report.abstained():
            print(f"  [UNCLEAR] {abstained['name']}: {abstained['error']}")
    else:
        print(
            "judge: not run (pass --judge-target with --email for a live judge, "
            "or --judge-outputs to replay a recording)"
        )

    for line in _threshold_lines(args, report):
        print(line)
    for reason in reasons:
        print(f"reason: {reason}")
    print(f"exit code: {exit_code}")


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: SessionFactory | None = None,
    adapter_factory: AdapterFactory | None = None,
) -> int:
    """Entry point. Returns a process exit code."""

    args = _parse_args(list(argv) if argv is not None else None)
    problem = _validate_args(args)
    if problem is not None:
        print(f"aegis: error: {problem}", file=sys.stderr)
        return 1

    try:
        items = _load_items(args.items)
    except ValueError as exc:
        print(f"aegis: error: {exc}", file=sys.stderr)
        return 1

    judge: JudgeCallable | None = None
    if args.judge_target is None and args.judge_outputs is not None:
        try:
            judge = _replay_judge(load_recorded_outputs(args.judge_outputs))
        except ValueError as exc:
            print(f"aegis: error: {exc}", file=sys.stderr)
            return 1

    judge_config: dict[str, str] | None = None
    try:
        if args.judge_target is not None:
            report, judge_model = asyncio.run(
                _run_live(args, items, session_factory, adapter_factory)
            )
            judge_config = {"target_id": str(args.judge_target), "model": judge_model}
        else:
            report = asyncio.run(run_calibration(items, judge=judge))
    except _CalibrationUsageError as exc:
        print(f"aegis: error: {exc}", file=sys.stderr)
        return 1
    except PermissionDeniedError as exc:
        print(f"aegis: error: {exc}", file=sys.stderr)
        return 1

    recorded: dict[str, object] | None = None
    if args.judge_target is not None and args.record is not None:
        count = write_recorded_outputs(args.record, report.results)
        recorded = {"path": str(args.record), "count": count}
        if not args.json:
            print(f"recorded: {count} judge outputs -> {args.record}")

    reasons, problems = _evaluate_thresholds(args, report)
    if problems:
        for message in problems:
            print(f"aegis: error: {message}", file=sys.stderr)
        return 1
    exit_code = 2 if reasons else 0

    if args.json:
        payload = report.to_dict()
        payload["thresholds"] = {
            "min_detector_recall": args.min_detector_recall,
            "min_judge_accuracy": args.min_judge_accuracy,
            "min_judge_recall": args.min_judge_recall,
        }
        payload["reasons"] = reasons
        payload["exit_code"] = exit_code
        payload["judge_config"] = judge_config
        if recorded is not None:
            payload["recorded"] = recorded
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_report(report, args, reasons, exit_code, judge_config)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

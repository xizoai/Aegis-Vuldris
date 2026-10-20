"""``python -m app.cli.grading_accuracy`` — measure grader false positives.

The suite's precision yardstick, made runnable. Every bundled test case is
graded against a corpus of responses a correctly-behaved model gives; any
finding is a false positive by construction. Monitoring this number turns
"precision" from a claim into a CI gate: a pattern change that starts
flagging refusals fails the build before it reaches anyone's report.

Exit codes:

    0  measured; the rate is within the threshold (or no threshold set)
    1  usage error (bad threshold)
    2  the measured false-positive rate exceeds --threshold
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.services.grading_accuracy import measure_false_positives


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.grading_accuracy",
        description=(
            "Grade known-safe model responses with every bundled test case "
            "and report every finding as a false positive."
        ),
    )
    parser.add_argument(
        "--test-case-dir",
        type=Path,
        default=None,
        help="Directory of attack cases to grade with. Defaults to the bundled library.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=(
            "Exit 2 when the false-positive rate exceeds this fraction "
            "(for example 0.01 for one percent). Use 0 in CI to fail on any "
            "false positive at all."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON for a CI job to consume.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""

    args = _parse_args(list(argv) if argv is not None else None)
    if args.threshold is not None and not 0 <= args.threshold <= 1:
        print("aegis: error: --threshold must be a fraction between 0 and 1")
        return 1

    report = measure_false_positives(test_case_dir=args.test_case_dir)
    exceeded = args.threshold is not None and report.false_positive_rate > args.threshold

    payload = {
        "responses_evaluated": report.responses_evaluated,
        "evaluations": report.evaluations,
        "false_positive_count": report.false_positive_count,
        "false_positive_rate": round(report.false_positive_rate, 6),
        "threshold": args.threshold,
        "threshold_exceeded": exceeded,
        "offenders": [
            {
                "response": item.response_name,
                "test_case": item.test_case,
                "matched_patterns": item.matched_patterns,
            }
            for item in report.false_positives
        ],
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"grading accuracy: {report.summary()}")
        for item in report.false_positives[:25]:
            patterns = ", ".join(item.matched_patterns) or "n/a"
            print(f"  [FALSE POSITIVE] {item.response_name} vs {item.test_case}: {patterns}")
        if len(report.false_positives) > 25:
            print(f"  … and {len(report.false_positives) - 25} more")
        if args.threshold is not None:
            verdict = "EXCEEDED" if exceeded else "ok"
            print(f"threshold: {args.threshold:g} - {verdict}")

    return 2 if exceeded else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Regression gate: compare finding sets and decide whether a run regressed.

The API's report comparison and the CLI's ``--baseline`` gate must never drift
apart — they are the same question ("what changed between these two finding
sets?") asked from two places. This module owns the answer:

- :func:`diff_findings` classifies two finding sets into new / resolved /
  regressed / improved / unchanged, matched by ``(test_category, title)``;
- :func:`evaluate_regression_gate` applies the CI contract to a diff: exit 2
  only on configured regressions (``--fail-on`` threshold, or any new /
  regressed finding without a threshold), never on inconclusive runs unless
  explicitly requested, and never on operational errors (those are handled
  by the caller as exit 4);
- :func:`load_baseline_file` reads a saved JSON report artifact so a CI job
  can gate against a file from a previous run without database access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.finding import FindingSeverity
from app.services.risk_scoring import severity_to_score

_REQUIRED_FINDING_KEYS = ("title", "test_category", "severity")


def _finding_key(finding: dict[str, Any]) -> str:
    return f"{finding.get('test_category', '')}|{finding.get('title', '')}"


def diff_findings(baseline: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    """Diff two finding sets by ``(test_category, title)``.

    Both sides are plain finding dicts as stored in report snapshots. A
    finding present only in ``current`` is new; only in ``baseline`` is
    resolved; in both with a higher severity in ``current`` is regressed
    (lower is improved; equal is unchanged).
    """

    before = {_finding_key(finding): finding for finding in baseline}
    after = {_finding_key(finding): finding for finding in current}

    new_findings: list[dict[str, Any]] = []
    resolved_findings: list[dict[str, Any]] = []
    regressed_findings: list[dict[str, Any]] = []
    improved_findings: list[dict[str, Any]] = []
    unchanged_findings: list[dict[str, Any]] = []

    for key, finding_b in after.items():
        finding_a = before.get(key)
        if finding_a is None:
            new_findings.append(finding_b)
            continue

        severity_before = finding_a["severity"]
        severity_after = finding_b["severity"]
        if severity_before == severity_after:
            unchanged_findings.append(finding_b)
            continue

        entry = {
            "title": finding_b["title"],
            "category": finding_b["test_category"],
            "severity_before": severity_before,
            "severity_after": severity_after,
            "owasp_category": finding_b.get("owasp_category", "N/A"),
        }
        if severity_to_score(FindingSeverity(severity_after)) > severity_to_score(
            FindingSeverity(severity_before)
        ):
            regressed_findings.append(entry)
        else:
            improved_findings.append(entry)

    for key, finding_a in before.items():
        if key not in after:
            resolved_findings.append(finding_a)

    return {
        "new_findings": new_findings,
        "resolved_findings": resolved_findings,
        "regressed_findings": regressed_findings,
        "improved_findings": improved_findings,
        "unchanged_findings": unchanged_findings,
        "new_count": len(new_findings),
        "resolved_count": len(resolved_findings),
        "regressed_count": len(regressed_findings),
        "improved_count": len(improved_findings),
        "unchanged_count": len(unchanged_findings),
    }


def regressions_at_or_above(diff: dict[str, Any], fail_on: str | None) -> list[dict[str, str]]:
    """The new and regressed findings that match a severity threshold.

    Without a threshold every new/regressed finding counts. With one, a
    regression only counts when its severity is at or above it — a new
    ``medium`` finding must not fail a gate configured for ``critical``.
    """

    threshold = severity_to_score(FindingSeverity(fail_on)) if fail_on else None
    matching: list[dict[str, str]] = []

    for finding in diff["new_findings"]:
        if (
            threshold is None
            or severity_to_score(FindingSeverity(finding["severity"])) >= threshold
        ):
            matching.append(
                {
                    "kind": "new",
                    "title": finding["title"],
                    "category": finding["test_category"],
                    "severity": finding["severity"],
                }
            )
    for entry in diff["regressed_findings"]:
        if (
            threshold is None
            or severity_to_score(FindingSeverity(entry["severity_after"])) >= threshold
        ):
            matching.append(
                {
                    "kind": "regressed",
                    "title": entry["title"],
                    "category": entry["category"],
                    "severity": entry["severity_after"],
                }
            )
    return matching


@dataclass(frozen=True)
class RegressionVerdict:
    """The gate's decision: exit 0 (clean) or 2 (configured regression)."""

    exit_code: int
    reasons: list[str] = field(default_factory=list)


def evaluate_regression_gate(
    diff: dict[str, Any],
    *,
    fail_on: str | None = None,
    inconclusive_count: int = 0,
    fail_on_inconclusive: bool = False,
) -> RegressionVerdict:
    """Apply the CI contract to a finding diff.

    Inconclusive runs are scanner honesty, not target behavior: they never
    fail the gate unless the caller explicitly asked for it.
    """

    regressions = regressions_at_or_above(diff, fail_on)
    reasons = [
        f"regression ({entry['kind']}): {entry['severity']} finding '{entry['title']}'"
        for entry in regressions
    ]

    if fail_on_inconclusive and inconclusive_count:
        reasons.append(
            f"inconclusive: {inconclusive_count} run(s) were inconclusive "
            "and --fail-on-inconclusive is set"
        )

    return RegressionVerdict(exit_code=2 if reasons else 0, reasons=reasons)


def load_baseline_file(path: Path) -> list[dict[str, Any]]:
    """Load findings from a saved JSON report artifact.

    ``aegis export --output report.json`` (or the report download endpoint)
    produces this shape. A file that is not a generated report is rejected
    with a clear message rather than an empty baseline, which would silently
    pass any gate.
    """

    with open(path, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from None

    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list):
        raise ValueError(
            f"{path} is not a generated Aegis Vuldris JSON report "
            "(expected a 'findings' array; generate one with 'aegis export')"
        )

    for finding in findings:
        if not isinstance(finding, dict) or any(
            key not in finding for key in _REQUIRED_FINDING_KEYS
        ):
            raise ValueError(
                f"{path} contains a malformed finding "
                f"(expected keys: {', '.join(_REQUIRED_FINDING_KEYS)})"
            )
    return findings

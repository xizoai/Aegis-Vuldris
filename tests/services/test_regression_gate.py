"""Regression gate tests: classification, thresholds, and the CI contract.

``services/regression.py`` owns the single diff implementation behind both
the API's report comparison and the CLI's ``--baseline`` gate, plus the
verdict rules: exit 2 only on configured regressions, never on inconclusive
runs unless explicitly requested, never on resolved or improved findings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.regression import (
    diff_findings,
    evaluate_regression_gate,
    load_baseline_file,
)


def _finding(title: str, severity: str, category: str = "prompt_injection") -> dict:
    return {"title": title, "test_category": category, "severity": severity}


def test_diff_findings_classifies_every_outcome() -> None:
    baseline = [
        _finding("Unchanged leak", "high"),
        _finding("Improved leak", "low"),
        _finding("Regressed leak", "high"),
        _finding("Resolved leak", "critical", category="jailbreak"),
    ]
    current = [
        _finding("Unchanged leak", "high"),
        _finding("Improved leak", "info"),
        _finding("Regressed leak", "critical"),
        _finding("New leak", "medium"),
    ]

    diff = diff_findings(baseline, current)

    assert diff["new_count"] == 1
    assert diff["new_findings"][0]["title"] == "New leak"
    assert diff["resolved_count"] == 1
    assert diff["resolved_findings"][0]["title"] == "Resolved leak"
    assert diff["regressed_count"] == 1
    assert diff["regressed_findings"][0] == {
        "title": "Regressed leak",
        "category": "prompt_injection",
        "severity_before": "high",
        "severity_after": "critical",
        "owasp_category": "N/A",
    }
    assert diff["improved_count"] == 1
    assert diff["improved_findings"][0]["severity_after"] == "info"
    assert diff["unchanged_count"] == 1


def test_diff_findings_matches_on_category_and_title_together() -> None:
    # Same title in a different category is a different finding, not a match.
    baseline = [_finding("Leak", "high", category="prompt_injection")]
    current = [_finding("Leak", "high", category="jailbreak")]

    diff = diff_findings(baseline, current)

    assert diff["new_count"] == 1
    assert diff["resolved_count"] == 1
    assert diff["unchanged_count"] == 0


def test_gate_fails_on_any_new_or_regressed_finding_without_threshold() -> None:
    diff = diff_findings([], [_finding("Brand new", "low")])
    verdict = evaluate_regression_gate(diff)
    assert verdict.exit_code == 2
    assert verdict.reasons == ["regression (new): low finding 'Brand new'"]


def test_gate_threshold_ignores_findings_below_it() -> None:
    diff = diff_findings([], [_finding("Only medium", "medium")])
    verdict = evaluate_regression_gate(diff, fail_on="critical")
    assert verdict.exit_code == 0
    assert verdict.reasons == []


def test_gate_threshold_matches_at_and_above_it() -> None:
    diff = diff_findings([_finding("Escalating", "high")], [_finding("Escalating", "critical")])
    verdict = evaluate_regression_gate(diff, fail_on="critical")
    assert verdict.exit_code == 2
    assert "regression (regressed): critical finding 'Escalating'" in verdict.reasons


def test_gate_never_fails_on_resolved_or_improved_findings() -> None:
    baseline = [_finding("Fixed by patch", "high"), _finding("Got better", "high")]
    current = [_finding("Got better", "low")]
    diff = diff_findings(baseline, current)

    verdict = evaluate_regression_gate(diff)
    assert verdict.exit_code == 0
    assert verdict.reasons == []


def test_gate_treats_inconclusive_as_scanner_honesty_not_failure() -> None:
    diff = diff_findings([], [])
    quiet = evaluate_regression_gate(diff, inconclusive_count=3)
    assert quiet.exit_code == 0

    strict = evaluate_regression_gate(diff, inconclusive_count=3, fail_on_inconclusive=True)
    assert strict.exit_code == 2
    assert len(strict.reasons) == 1
    assert "inconclusive" in strict.reasons[0]


def test_load_baseline_file_reads_a_generated_report(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_text(
        json.dumps(
            {
                "project_name": "demo",
                "findings": [_finding("Saved leak", "high")],
            }
        ),
        encoding="utf-8",
    )

    findings = load_baseline_file(artifact)
    assert findings[0]["title"] == "Saved leak"


def test_load_baseline_file_rejects_files_that_are_not_reports(tmp_path: Path) -> None:
    not_json = tmp_path / "not-json.txt"
    not_json.write_text("this is not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_baseline_file(not_json)

    not_a_report = tmp_path / "other.json"
    not_a_report.write_text(json.dumps({"hello": ["world"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a generated Aegis Vuldris JSON report"):
        load_baseline_file(not_a_report)

    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps({"findings": [{"title": "missing keys"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="malformed finding"):
        load_baseline_file(malformed)

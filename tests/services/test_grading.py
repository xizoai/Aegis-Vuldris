"""Tests for replaceable deterministic response graders."""

import pytest
from app.models.execution import ExecutionResult
from app.services.grading import DeterministicResponseGrader, GraderRegistry


def test_deterministic_grader_records_its_reproducible_identity() -> None:
    decision = DeterministicResponseGrader().grade(
        "The secret is canary-value.",
        {"grading": {"patterns": ["secret"], "severity": "high"}},
    )

    assert decision.result == ExecutionResult.FAIL
    assert decision.findings
    assert decision.grader_id == "aegis.deterministic-rules"
    assert decision.findings[0].details["grader"]["version"] == decision.grader_version


def test_grader_registry_rejects_ambiguous_registration() -> None:
    registry = GraderRegistry()
    registry.register("deterministic", DeterministicResponseGrader())

    with pytest.raises(ValueError, match="duplicate or empty"):
        registry.register("deterministic", DeterministicResponseGrader())

    with pytest.raises(KeyError, match="unknown grader"):
        registry.get("missing")

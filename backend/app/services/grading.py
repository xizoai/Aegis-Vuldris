"""Replaceable graders for assessment responses.

The execution engine depends on this small protocol, not on one classifier
implementation. Built-in grading remains deterministic and offline; optional
model judges continue to be orchestrated by the engine because they require a
separately configured target adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.execution import ExecutionResult
from app.services.finding_classifier import (
    DETERMINISTIC_GRADER_ID,
    DETERMINISTIC_GRADER_VERSION,
    ClassifiedFinding,
    classify_response,
    determine_execution_result,
)


@dataclass(frozen=True)
class GradingDecision:
    """A reproducible result from a response grader."""

    result: ExecutionResult
    findings: tuple[ClassifiedFinding, ...]
    grader_id: str
    grader_version: str


class ResponseGrader(Protocol):
    """Contract for a response-only grader.

    Graders receive normalized response text and a validated test config. They
    do not receive credentials, HTTP clients, sessions, or authorization
    objects, so a replacement grader cannot bypass those boundaries.
    """

    def grade(self, response_output: str, test_config: dict | None) -> GradingDecision:
        """Evaluate a response and return findings plus a semantic outcome."""

        ...


class DeterministicResponseGrader:
    """Built-in pattern and regex grader with refusal-aware evidence."""

    grader_id = DETERMINISTIC_GRADER_ID
    grader_version = DETERMINISTIC_GRADER_VERSION

    def grade(self, response_output: str, test_config: dict | None) -> GradingDecision:
        findings = tuple(classify_response(response_output, test_config))
        return GradingDecision(
            result=determine_execution_result(list(findings), test_config),
            findings=findings,
            grader_id=self.grader_id,
            grader_version=self.grader_version,
        )


class GraderRegistry:
    """Small internal registry for explicitly configured graders."""

    def __init__(self) -> None:
        self._graders: dict[str, ResponseGrader] = {}

    def register(self, name: str, grader: ResponseGrader) -> None:
        if not name or name in self._graders:
            raise ValueError(f"duplicate or empty grader name: {name!r}")
        self._graders[name] = grader

    def get(self, name: str) -> ResponseGrader:
        try:
            return self._graders[name]
        except KeyError as exc:
            raise KeyError(f"unknown grader: {name!r}") from exc


def built_in_graders() -> GraderRegistry:
    """Return a fresh registry containing only the built-in deterministic grader."""

    registry = GraderRegistry()
    registry.register("deterministic", DeterministicResponseGrader())
    return registry


__all__ = [
    "DeterministicResponseGrader",
    "GraderRegistry",
    "GradingDecision",
    "ResponseGrader",
    "built_in_graders",
]

"""A fixture third-party plugin used to prove entry-point discovery.

This module is the runnable example from ``docs/extension-points.md``: it
implements all four extension contracts in the smallest honest way. Tests copy
it into a temporary directory together with a hand-crafted ``.dist-info`` so
``importlib.metadata`` discovers it through the real entry-point machinery —
no fake registries, no monkeypatched loaders.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.base import BaseTargetAdapter
from app.models.execution import ExecutionResult
from app.models.model import ModelRequest, ModelResponse
from app.models.target import Target, TargetProvider
from app.services.grading import GradingDecision

# The version of the Aegis Vuldris extension contract this plugin was written for.
PLUGIN_API_VERSION = 1


class FixtureAlwaysPassGrader:
    """A deterministic grader that passes every response with no findings.

    Deterministic and side-effect free on purpose: a test fixture must never
    depend on a live model.
    """

    PLUGIN_API_VERSION = 1

    grader_id = "fixture/always-pass"
    grader_version = "0.1.0"

    def grade(self, response_output: str, test_config: dict | None) -> GradingDecision:
        return GradingDecision(
            result=ExecutionResult.PASS,
            findings=(),
            grader_id=self.grader_id,
            grader_version=self.grader_version,
        )


class FixtureTextExporter:
    """A report exporter writing a plain-text artifact for format ``txt``."""

    PLUGIN_API_VERSION = 1
    format = "txt"

    def write_artifact(self, data: dict[str, Any], out_dir: Path) -> Path:
        base = f"report_{data['report_id']}_v{data['report_version']}"
        path = out_dir / f"{base}.txt"
        lines = [
            "Aegis Vuldris fixture report",
            f"Project: {data.get('project_name')}",
            f"Total findings: {data.get('total_findings')}",
        ]
        for finding in data.get("findings", []):
            lines.append(f"- [{finding['severity']}] {finding['title']}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


class FixtureAttackCases:
    """Attack extensions are data: this points at a directory of YAML cases."""

    PLUGIN_API_VERSION = 1

    def __init__(self, cases_dir: str | Path) -> None:
        self.cases_dir = Path(cases_dir)


class FixtureAdapterBundle:
    """An adapter override bundle for the openai_compatible provider value."""

    PLUGIN_API_VERSION = 1
    provider = "openai_compatible"

    @staticmethod
    def factory(*, credential_resolver: Any = None, client: Any = None) -> BaseTargetAdapter:
        return FixtureAdapter(credential_resolver=credential_resolver, client=client)


class FixtureAdapter(BaseTargetAdapter):
    """A minimal adapter that answers every request with a fixed string."""

    provider = TargetProvider.OPENAI_COMPATIBLE

    async def _generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None,
    ) -> ModelResponse:
        return ModelResponse(output="fixture adapter response", finish_reason="stop")


# The names the entry points in the fixture dist-info resolve to. Instances,
# not classes: discovery loads exactly what the entry point names.
FIXTURE_GRADER = FixtureAlwaysPassGrader()
FIXTURE_EXPORTER = FixtureTextExporter()
FIXTURE_ATTACKS = FixtureAttackCases(Path(__file__).resolve().parent / "fixture_cases")
FIXTURE_ADAPTER_BUNDLE = FixtureAdapterBundle

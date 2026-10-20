"""Guards for the shipped GitHub Action.

The action is the CI contract other repositories consume, so its YAML must
parse, its documented inputs must exist, and — most importantly — it must
propagate the CLI exit code unchanged: a workflow that remaps exit 2 to 0
would silently pass regressions, and one that remaps 4 to 2 would lie about
scanner failures being findings.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTION_PATH = REPO_ROOT / "integration" / "github-action" / "action.yml"


def _action() -> dict:
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


def test_action_declares_documented_inputs() -> None:
    action = _action()
    inputs = action["inputs"]
    for name in (
        "project",
        "target",
        "email",
        "database-url",
        "secret-key",
        "image",
        "fail-on",
        "baseline",
        "fail-on-inconclusive",
    ):
        assert name in inputs, f"action input {name} is documented but missing"
    assert inputs["image"]["required"] is True, (
        "no official image is published yet; an explicit image input keeps the action honest"
    )


def test_action_runs_the_cli_and_preserves_exit_codes() -> None:
    action = _action()
    assert action["runs"]["using"] == "composite"
    script = action["runs"]["steps"][0]["run"]

    assert "aegis run" in script
    assert "--fail-on" in script
    assert "--baseline" in script
    assert "--fail-on-inconclusive" in script
    assert "--json" in script
    # The summary lands on the pull request page.
    assert "GITHUB_STEP_SUMMARY" in script
    # The exit code is captured and propagated, never remapped: 2 must stay
    # a configured regression and 4 an operational error.
    assert "status=$?" in script
    assert 'exit "$status"' in script

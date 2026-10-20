"""Run garak against the Aegis LLM shim and normalize its report.

garak scans a target by talking to it through a generator. Here the generator is
pointed at the Aegis LLM shim rather than at the target, so the shim keeps
resolving credentials and applying the network policy: garak receives no API key
and no target URL. The scan token is the only secret the runner holds.

The module is split into pure pieces -- the generator config, the command line,
and the report parser -- and one impure function that shells out. The pure
pieces are what the tests exercise, so the runner's behaviour is pinned without
a garak installation in CI.

Two things must be checked against the pinned garak in the runner image before a
real scan is trusted (see ``docs/integration-plan-garak-pyrit.md`` section 4.4):

- The ``rest`` generator config file shape. garak's exact nesting has changed
  across releases; the file written here is the shape documented for 0.17.1 and
  is overridable through ``config["generator_option_file"]`` so a deployment can
  ship a hand-verified file instead.
- The ``report.jsonl`` attempt record keys. The parser reads them defensively
  and treats anything it cannot judge as ``inconclusive`` rather than as a pass.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# A small default set, chosen to exercise three distinct probe families without
# turning a first scan into an hours-long run. Operators widen it through the
# scan's config.
DEFAULT_PROBES: tuple[str, ...] = (
    "dan.Dan_11_0",
    "promptinject.HijackHateHumans",
)

# Probe families a scan may select. This is an allow-list rather than a filter:
# a config naming anything else fails the scan instead of silently running
# whatever the API was asked for. The expensive and GPU-hungry families
# (atkgen, audio, dra, gcg) are deliberately absent; adding one is a deliberate
# capacity decision, not a config value.
ALLOWED_PROBE_FAMILIES: frozenset[str] = frozenset(
    {
        "continuation",
        "dan",
        "encoding",
        "goodside",
        "knownbadsignatures",
        "leakreplay",
        "lmrc",
        "malwaregen",
        "packagehallucination",
        "promptinject",
        "realtoxicityprompts",
        "snowball",
        "xss",
    }
)

# Bounds a single scan's probe selection. Each probe runs many attempts, so the
# cap is on the selection rather than on a per-attempt count.
MAX_PROBES = 20

_REPORT_SUFFIX = ".report.jsonl"
_VERSION_PATTERN = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


class GarakError(RuntimeError):
    """Raised when garak cannot be configured, run, or read."""


@dataclass(frozen=True)
class GarakAttempt:
    """One judged attempt from a garak report."""

    probe: str
    detector: str | None
    verdict: str
    trigger_count: int
    record_index: int


def validate_probes(probes: Sequence[str] | None) -> list[str]:
    """Return a safe probe selection, rejecting anything outside the allow-list."""

    selection = [probe.strip() for probe in (probes or DEFAULT_PROBES) if probe.strip()]
    if not selection:
        selection = list(DEFAULT_PROBES)
    if len(selection) > MAX_PROBES:
        raise GarakError(f"at most {MAX_PROBES} probes may be selected, got {len(selection)}")

    for probe in selection:
        family = probe.partition(".")[0].lower()
        if family not in ALLOWED_PROBE_FAMILIES:
            raise GarakError(f"probe family {family!r} is not allowed")

    return selection


def build_rest_generator_config(
    *,
    shim_url: str,
    scan_token: str,
    model_name: str,
) -> dict[str, Any]:
    """Build the garak ``rest`` generator config for the Aegis shim.

    The token appears only here, in a file the runner writes to its own
    workspace with owner-only permissions and deletes after the run. It is
    never passed on the command line, where it would be visible to any other
    process on the host through the process list.
    """

    return {
        "rest": {
            "RestGenerator": {
                "name": f"aegis-shim:{model_name}",
                "uri": shim_url,
                "method": "post",
                "headers": {
                    "Authorization": f"Bearer {scan_token}",
                    "Content-Type": "application/json",
                },
                # garak fills these per attempt; the shim accepts exactly this
                # shape and rejects anything carrying a destination.
                "req_template_json_object": {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "$INPUT"}],
                },
                "response_json": True,
                "response_json_field": "$.choices[0].message.content",
                "request_timeout": 120,
                # A refused call (bad token, policy block, provider error) is a
                # scan-level problem: garak should stop rather than record the
                # error body as a model response that then "passes" detectors.
                "skip_codes": [],
            }
        }
    }


def build_command(
    *,
    command: Sequence[str],
    probes: Sequence[str],
    model_config_path: Path,
    report_prefix: Path,
    seed: int | None = None,
) -> list[str]:
    """Build the garak command line for one scan."""

    argv = [
        *command,
        "--model_type",
        "rest",
        "--model_name",
        str(model_config_path),
        "--probes",
        ",".join(probes),
        "--report_prefix",
        str(report_prefix),
    ]
    if seed is not None:
        argv.extend(["--seed", str(seed)])
    return argv


def report_path_for(report_prefix: Path) -> Path:
    """Return where garak writes its JSONL report for a prefix."""

    return report_prefix.with_name(report_prefix.name + _REPORT_SUFFIX)


def parse_report(lines: Iterable[str]) -> list[GarakAttempt]:
    """Map a garak ``report.jsonl`` to attempts.

    Only ``entry_type == "attempt"`` records are attempts; the report also
    carries run metadata (init, start, eval, end) that has no verdict.

    A line that is not JSON, or an attempt with no probe id, raises: the report
    is machine-written, so a malformed line means the run is not trustworthy and
    guessing past it could hide a finding.
    """

    attempts: list[GarakAttempt] = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GarakError(f"report line {index} is not valid JSON: {exc}") from exc
        if not isinstance(entry, dict) or entry.get("entry_type") != "attempt":
            continue

        probe = entry.get("probe") or entry.get("probe_name")
        if not isinstance(probe, str) or not probe.strip():
            raise GarakError(f"report line {index} is an attempt with no probe id")

        detector = entry.get("detector")
        passed = entry.get("passed")
        if passed is True or passed == 1:
            verdict = "pass"
        elif passed is False or passed == 0:
            verdict = "fail"
        else:
            # No usable verdict (a detector that errored, a truncated record).
            # Never a pass: the plan forbids reporting an unknown as success.
            verdict = "inconclusive"

        trigger = entry.get("trigger")
        trigger_count = len(trigger) if isinstance(trigger, list) else 0

        attempts.append(
            GarakAttempt(
                probe=probe.strip(),
                detector=detector.strip()
                if isinstance(detector, str) and detector.strip()
                else None,
                verdict=verdict,
                trigger_count=trigger_count,
                record_index=index,
            )
        )

    return attempts


def to_scan_results(attempts: Iterable[GarakAttempt]) -> list[dict[str, Any]]:
    """Convert attempts into the API's result records.

    No prompts, outputs, or triggering strings are copied: they are attack
    content and, when a probe works, the leaked data itself. The raw report
    keeps them under the retention-managed report volume.
    """

    return [
        {
            "probe": attempt.probe,
            "detector": attempt.detector,
            "verdict": attempt.verdict,
            "trigger_count": attempt.trigger_count,
            "record_index": attempt.record_index,
        }
        for attempt in attempts
    ]


def _default_command() -> list[str]:
    """Return the configured garak command.

    ``python -m garak`` rather than ``garak``: it uses the interpreter the
    runner is already running under, so a scan cannot accidentally use a garak
    installed elsewhere on the host.
    """

    configured = os.environ.get("AEGIS_GARAK_COMMAND", "").strip()
    if configured:
        return shlex.split(configured)
    return [sys.executable, "-m", "garak"]


def garak_version(command: Sequence[str] | None = None) -> str | None:
    """Return garak's reported version, or None when it cannot be read."""

    argv = [*(command or _default_command()), "--version"]
    try:
        completed = subprocess.run(  # noqa: S603 - argv, never a shell string
            argv,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    match = _VERSION_PATTERN.search(completed.stdout or "")
    return match.group(1) if match else None


def run_garak(
    *,
    shim_url: str,
    scan_token: str,
    model_name: str,
    probes: Sequence[str] | None,
    report_dir: Path,
    scan_id: str,
    seed: int | None = None,
    command: Sequence[str] | None = None,
    timeout: float = 0,
    generator_option_file: str | None = None,
) -> tuple[Path, list[dict[str, Any]], str | None]:
    """Run garak and return (report path, result records, tool version).

    ``generator_option_file`` short-circuits config generation: a deployment can
    point at a hand-verified garak generator file, which is also the escape
    hatch when the generated shape does not match the pinned garak release.
    """

    argv_base = list(command or _default_command())
    selected = validate_probes(probes)
    version = garak_version(argv_base)

    report_dir.mkdir(parents=True, exist_ok=True)
    report_prefix = report_dir / f"scan-{scan_id}"
    report_path = report_path_for(report_prefix)

    with tempfile.TemporaryDirectory(prefix="aegis-garak-") as workspace:
        if generator_option_file:
            model_config_path = Path(generator_option_file)
        else:
            model_config_path = _write_generator_config(
                Path(workspace),
                shim_url=shim_url,
                scan_token=scan_token,
                model_name=model_name,
            )

        argv = build_command(
            command=argv_base,
            probes=selected,
            model_config_path=model_config_path,
            report_prefix=report_prefix,
            seed=seed,
        )

        try:
            completed = subprocess.run(  # noqa: S603 - argv, never a shell string
                argv,
                capture_output=True,
                text=True,
                timeout=timeout or None,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GarakError(f"garak could not be started: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise GarakError(f"garak exceeded its time budget ({timeout}s)") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-1000:]
            raise GarakError(f"garak exited with {completed.returncode}: {detail}")

    if not report_path.exists():
        raise GarakError(f"garak produced no report at {report_path.name}")

    attempts = parse_report(report_path.read_text(encoding="utf-8").splitlines())

    return report_path, to_scan_results(attempts), version


def _write_generator_config(
    workspace: Path,
    *,
    shim_url: str,
    scan_token: str,
    model_name: str,
) -> Path:
    """Write the generator config with owner-only permissions."""

    config = build_rest_generator_config(
        shim_url=shim_url,
        scan_token=scan_token,
        model_name=model_name,
    )
    path = workspace / "rest-generator.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best effort: the file lives in a private temp directory either way,
        # and this cannot be enforced on every platform.
        pass
    return path


__all__ = [
    "ALLOWED_PROBE_FAMILIES",
    "DEFAULT_PROBES",
    "MAX_PROBES",
    "GarakAttempt",
    "GarakError",
    "build_command",
    "build_rest_generator_config",
    "garak_version",
    "parse_report",
    "report_path_for",
    "run_garak",
    "to_scan_results",
    "validate_probes",
]

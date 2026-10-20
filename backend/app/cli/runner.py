"""``python -m app.cli.runner`` -- claim and run external scans.

The runner claims a job, executes the claimed tool, and reports one terminal
result. garak runs against the Aegis LLM shim (``app/cli/garak.py``), so the
runner needs neither target credentials nor a target URL -- only the scan-scoped
token it received with the claim.

The runner deliberately imports no application settings or database code. It
talks to the API over HTTP and holds only the runner service token, so a
compromised runner has no target credentials and no database access.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any

import httpx2

from app.cli.garak import GarakError, garak_version, run_garak

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_REPORT_DIR = "scan-reports"


class UnsupportedToolError(RuntimeError):
    """Raised for a tool this runner does not implement yet."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.runner",
        description="Claim external scans from AegisAI and report their result.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("AEGIS_API_URL", DEFAULT_API_URL),
        help="AegisAI API base URL.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("RUNNER_SERVICE_TOKEN", ""),
        help="Runner service token. Defaults to RUNNER_SERVICE_TOKEN.",
    )
    parser.add_argument(
        "--report-dir",
        default=os.environ.get("AEGIS_SCAN_REPORT_DIR", DEFAULT_REPORT_DIR),
        help=(
            "Directory for raw tool reports. Point this at the same volume as "
            "the API's AEGIS_REPORT_DIR so retention can purge them."
        ),
    )
    parser.add_argument(
        "--garak-command",
        default=os.environ.get("AEGIS_GARAK_COMMAND", ""),
        help=(
            "garak command line, e.g. 'python -m garak'. Defaults to the "
            "runner's own interpreter running the garak module."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim at most one scan and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds to wait between empty claims.",
    )
    parser.add_argument(
        "--noop-seconds",
        type=float,
        default=0.0,
        help=(
            "Simulate work instead of running a tool, for exercising the queue "
            "without a scan target."
        ),
    )
    return parser.parse_args(argv)


def shim_url_for(api_url: str, scan_id: str) -> str:
    """Return the shim endpoint garak should be pointed at for a scan."""

    return f"{api_url.rstrip('/')}/api/v1/external/llm/{scan_id}/v1/chat/completions"


def run_scan(
    scan: dict[str, Any],
    *,
    api_url: str,
    llm_token: str | None,
    report_dir: Path,
    noop_seconds: float = 0.0,
    garak_command: list[str] | None = None,
) -> dict[str, Any]:
    """Execute a claimed scan and return the completion payload.

    Dispatches on ``scan["tool"]``. Every tool sends its normalized verdicts in
    the completion payload, so the API ingests findings in the same call that
    records the terminal state.
    """

    if noop_seconds > 0:
        time.sleep(noop_seconds)
        return {
            "status": "completed",
            "external_run_id": f"noop-{scan['id']}",
        }

    tool = scan.get("tool")

    if tool == "garak":
        return _run_garak_scan(
            scan,
            api_url=api_url,
            llm_token=llm_token,
            report_dir=report_dir,
            garak_command=garak_command,
        )

    if tool == "pyrit":
        raise UnsupportedToolError("PyRIT scans are not implemented yet (phase 3)")

    raise UnsupportedToolError(f"unsupported scan tool: {tool!r}")


def _run_garak_scan(
    scan: dict[str, Any],
    *,
    api_url: str,
    llm_token: str | None,
    report_dir: Path,
    garak_command: list[str] | None,
) -> dict[str, Any]:
    """Run garak against the shim and build the completion payload."""

    if not llm_token:
        raise GarakError("claim returned no scan token; the shim cannot be called without one")

    config = scan.get("config") or {}
    command = garak_command or None

    report_path, results, version = run_garak(
        shim_url=shim_url_for(api_url, scan["id"]),
        scan_token=llm_token,
        model_name=str(config.get("model_name") or "aegis-scan"),
        probes=config.get("probes"),
        report_dir=report_dir,
        scan_id=scan["id"],
        seed=config.get("seed"),
        command=command,
        generator_option_file=config.get("generator_option_file"),
    )

    return {
        "status": "completed",
        "tool_version": version or garak_version(command),
        "external_run_id": f"garak-{scan['id']}",
        "report_path": str(report_path),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.token.strip():
        print("RUNNER_SERVICE_TOKEN (or --token) is required.", file=sys.stderr)
        return 2

    report_dir = Path(args.report_dir)
    garak_command = shlex.split(args.garak_command) if args.garak_command.strip() else None
    headers = {"Authorization": f"Bearer {args.token}"}

    with httpx2.Client(
        base_url=args.api_url.rstrip("/"),
        headers=headers,
        # A scan runs for minutes; the claim and report calls themselves stay
        # short, but the client is shared and must not abandon a slow response.
        timeout=60.0,
    ) as client:
        while True:
            try:
                claim = client.post("/api/v1/internal/scans/claim")
                claim.raise_for_status()
            except httpx2.HTTPError as exc:
                print(f"claim failed: {exc}", file=sys.stderr)
                if args.once:
                    return 1
                time.sleep(args.poll_interval)
                continue

            claim_body = claim.json()
            scan = claim_body.get("scan")

            if scan is None:
                if args.once:
                    print("no queued scans")
                    return 0
                time.sleep(args.poll_interval)
                continue

            if scan["status"] != "running":
                # The API fails a scan it cannot hand out (for example one whose
                # target was deleted after queueing) and returns it claimed but
                # already terminal. Nothing to run, and reporting again would be
                # a conflict rather than a result.
                print(
                    json.dumps({"skipped": scan["id"], "status": scan["status"]}),
                    flush=True,
                )
                if args.once:
                    return 0
                continue

            print(json.dumps({"claimed": scan["id"], "tool": scan["tool"]}), flush=True)

            try:
                payload = run_scan(
                    scan,
                    api_url=args.api_url,
                    llm_token=claim_body.get("llm_token"),
                    report_dir=report_dir,
                    noop_seconds=args.noop_seconds,
                    garak_command=garak_command,
                )
            except Exception as exc:  # noqa: BLE001 - reported to the API, not swallowed
                payload = {"status": "failed", "error": str(exc)[:4000]}

            try:
                report = client.post(
                    f"/api/v1/internal/scans/{scan['id']}/complete",
                    json=payload,
                )
                report.raise_for_status()
            except httpx2.HTTPError as exc:
                print(f"report failed for {scan['id']}: {exc}", file=sys.stderr)
                if args.once:
                    return 1
                continue

            print(
                json.dumps({"completed": scan["id"], "status": report.json()["status"]}),
                flush=True,
            )

            if args.once:
                return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

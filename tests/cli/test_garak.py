"""Runner-side garak tests: config, command, report parsing, and dispatch.

A stub garak stands in for the real tool. It is invoked exactly as garak is
(argv, and a config file passed through --model_name), reads that config, and
writes a report with the same JSONL entry types a real run emits. That keeps the
contract the runner depends on pinned in CI without installing garak.
"""

import json
import sys
from pathlib import Path

import pytest
from app.cli.garak import (
    DEFAULT_PROBES,
    MAX_PROBES,
    GarakError,
    build_command,
    build_rest_generator_config,
    parse_report,
    report_path_for,
    run_garak,
    to_scan_results,
    validate_probes,
)
from app.cli.runner import UnsupportedToolError, run_scan, shim_url_for

SHIM_URL = "http://aegis.test/api/v1/external/llm/scan-1/v1/chat/completions"

# Writes <prefix>.report.jsonl next to the report prefix, plus a .seen.json
# recording the argv and the generator config it was handed, so a test can
# assert what garak actually received.
_FAKE_GARAK = """\
import json
import sys
from pathlib import Path

argv = sys.argv[1:]

if "--version" in argv:
    print("garak LLM vulnerability scanner v0.17.1 ( https://github.com/NVIDIA/garak )")
    raise SystemExit(0)

prefix = None
config_path = None
for index, arg in enumerate(argv):
    if arg == "--report_prefix":
        prefix = argv[index + 1]
    elif arg == "--model_name":
        config_path = argv[index + 1]

if prefix is None:
    print("no --report_prefix", file=sys.stderr)
    raise SystemExit(2)

base = Path(prefix)
config_text = Path(config_path).read_text(encoding="utf-8") if config_path else None
base.with_name(base.name + ".seen.json").write_text(
    json.dumps({"argv": argv, "config": config_text}), encoding="utf-8"
)

lines = [
    {"entry_type": "init", "garak_version": "0.17.1"},
    {
        "entry_type": "attempt",
        "probe": "dan.Dan_11_0",
        "detector": "dan.DAN",
        "passed": 0,
        "trigger": ["here is how", "step one"],
        "prompt": "attack prompt that must not reach the API",
        "outputs": ["model output that must not reach the API"],
    },
    {
        "entry_type": "attempt",
        "probe": "promptinject.HijackHateHumans",
        "detector": "promptinject.AttackRogueString",
        "passed": 1,
        "trigger": [],
    },
    {
        "entry_type": "attempt",
        "probe": "encoding.InjectBase64",
        "detector": "encoding.DecodeMatch",
        "status": 1,
    },
    {"entry_type": "end"},
]
base.with_name(base.name + ".report.jsonl").write_text(
    "\\n".join(json.dumps(line) for line in lines), encoding="utf-8"
)
"""


@pytest.fixture
def fake_garak(tmp_path: Path) -> list[str]:
    """Return a command line for a stub garak."""

    script = tmp_path / "fake_garak.py"
    script.write_text(_FAKE_GARAK, encoding="utf-8")
    return [sys.executable, str(script)]


def _seen(report_path: Path) -> dict:
    seen = report_path.with_name(report_path.name.replace(".report.jsonl", ".seen.json"))
    return json.loads(seen.read_text(encoding="utf-8"))


# --- generator config -------------------------------------------------------


def test_generator_config_points_at_the_shim_and_names_no_target() -> None:
    config = build_rest_generator_config(
        shim_url=SHIM_URL,
        scan_token="scan-token-value",
        model_name="team-model",
    )

    rest = config["rest"]["RestGenerator"]
    assert rest["uri"] == SHIM_URL
    assert rest["method"] == "post"
    assert rest["headers"]["Authorization"] == "Bearer scan-token-value"
    assert rest["response_json"] is True
    assert rest["response_json_field"] == "$.choices[0].message.content"
    assert rest["req_template_json_object"]["messages"][0]["content"] == "$INPUT"

    # The runner never learns, and so never passes on, a target URL or key.
    serialized = json.dumps(config)
    assert "model.example" not in serialized
    assert "api_key" not in serialized


def test_report_path_appends_the_garak_suffix() -> None:
    assert report_path_for(Path("/reports/scan-1")).name == "scan-1.report.jsonl"


# --- probe selection --------------------------------------------------------


def test_probes_default_when_the_config_names_none() -> None:
    assert validate_probes(None) == list(DEFAULT_PROBES)
    assert validate_probes([]) == list(DEFAULT_PROBES)


def test_allowed_probe_families_pass_through() -> None:
    assert validate_probes(["dan.Dan_11_0", "encoding", "leakreplay.GuardianCloze"]) == [
        "dan.Dan_11_0",
        "encoding",
        "leakreplay.GuardianCloze",
    ]


def test_probe_outside_the_allow_list_is_refused() -> None:
    with pytest.raises(GarakError, match="not allowed"):
        validate_probes(["atkgen.Tox"])
    with pytest.raises(GarakError, match="not allowed"):
        validate_probes(["dra.anything"])
    with pytest.raises(GarakError, match="not allowed"):
        validate_probes(["encoding", "gcg.SomeProbe"])


def test_probe_selection_is_bounded() -> None:
    with pytest.raises(GarakError, match="at most"):
        validate_probes([f"dan.Probe{i}" for i in range(MAX_PROBES + 1)])


# --- command line -----------------------------------------------------------


def test_command_uses_the_rest_generator_and_the_report_prefix() -> None:
    argv = build_command(
        command=["python", "-m", "garak"],
        probes=["dan.Dan_11_0", "xss.MarkdownImage"],
        model_config_path=Path("/w/rest.json"),
        report_prefix=Path("/reports/scan-1"),
        seed=7,
    )

    assert argv[:3] == ["python", "-m", "garak"]
    assert argv[argv.index("--model_type") + 1] == "rest"
    assert argv[argv.index("--model_name") + 1] == str(Path("/w/rest.json"))
    assert argv[argv.index("--probes") + 1] == "dan.Dan_11_0,xss.MarkdownImage"
    assert argv[argv.index("--report_prefix") + 1] == str(Path("/reports/scan-1"))
    assert argv[argv.index("--seed") + 1] == "7"


def test_command_omits_the_seed_when_unset() -> None:
    argv = build_command(
        command=["garak"],
        probes=["dan"],
        model_config_path=Path("/w/rest.json"),
        report_prefix=Path("/reports/scan-1"),
    )

    assert "--seed" not in argv


# --- report parsing ---------------------------------------------------------


def test_parse_report_maps_three_verdicts_and_skips_run_metadata() -> None:
    lines = [
        json.dumps({"entry_type": "init"}),
        json.dumps(
            {
                "entry_type": "attempt",
                "probe": "dan.Dan_11_0",
                "detector": "dan.DAN",
                "passed": 0,
                "trigger": ["a", "b"],
            }
        ),
        json.dumps(
            {
                "entry_type": "attempt",
                "probe": "promptinject.HijackHateHumans",
                "detector": "promptinject.AttackRogueString",
                "passed": 1,
                "trigger": [],
            }
        ),
        json.dumps({"entry_type": "attempt", "probe": "encoding.InjectBase64", "status": 1}),
        json.dumps({"entry_type": "end"}),
        "",
    ]

    attempts = parse_report(lines)

    assert [attempt.verdict for attempt in attempts] == ["fail", "pass", "inconclusive"]
    assert [attempt.probe for attempt in attempts] == [
        "dan.Dan_11_0",
        "promptinject.HijackHateHumans",
        "encoding.InjectBase64",
    ]
    assert attempts[0].trigger_count == 2
    assert attempts[2].detector is None
    # record_index is the line number, so a finding can be traced to its record.
    assert [attempt.record_index for attempt in attempts] == [1, 2, 3]


def test_parse_report_rejects_a_malformed_line() -> None:
    with pytest.raises(GarakError, match="not valid JSON"):
        parse_report(["not json at all"])

    with pytest.raises(GarakError, match="no probe id"):
        parse_report([json.dumps({"entry_type": "attempt", "detector": "d"})])


def test_scan_results_carry_no_prompt_or_output_content() -> None:
    attempts = parse_report(
        [
            json.dumps(
                {
                    "entry_type": "attempt",
                    "probe": "dan.Dan_11_0",
                    "detector": "dan.DAN",
                    "passed": 0,
                    "trigger": ["leaked secret"],
                    "prompt": "attack prompt",
                    "outputs": ["model output"],
                }
            )
        ]
    )

    results = to_scan_results(attempts)

    assert results == [
        {
            "probe": "dan.Dan_11_0",
            "detector": "dan.DAN",
            "verdict": "fail",
            "trigger_count": 1,
            "record_index": 0,
        }
    ]
    serialized = json.dumps(results)
    assert "leaked secret" not in serialized
    assert "attack prompt" not in serialized
    assert "model output" not in serialized


# --- invocation -------------------------------------------------------------


def test_run_garak_passes_the_token_in_a_file_not_the_command_line(
    tmp_path: Path, fake_garak: list[str]
) -> None:
    report_path, results, version = run_garak(
        shim_url=SHIM_URL,
        scan_token="super-secret-token",
        model_name="team-model",
        probes=["dan.Dan_11_0"],
        report_dir=tmp_path / "reports",
        scan_id="1",
        command=fake_garak,
    )

    assert version == "0.17.1"
    assert report_path.name == "scan-1.report.jsonl"
    assert [result["verdict"] for result in results] == ["fail", "pass", "inconclusive"]

    seen = _seen(report_path)
    config = json.loads(seen["config"])
    assert config["rest"]["RestGenerator"]["headers"]["Authorization"] == (
        "Bearer super-secret-token"
    )
    assert config["rest"]["RestGenerator"]["uri"] == SHIM_URL
    # The command line never carries the token.
    assert "super-secret-token" not in seen["argv"]
    assert seen["argv"][seen["argv"].index("--probes") + 1] == "dan.Dan_11_0"

    # The generated config is a temporary file and does not outlive the run.
    leftovers = sorted(path.name for path in (tmp_path / "reports").iterdir())
    assert leftovers == ["scan-1.report.jsonl", "scan-1.seen.json"]


def test_run_garak_writes_nothing_secret_when_a_config_file_is_supplied(
    tmp_path: Path, fake_garak: list[str]
) -> None:
    supplied = tmp_path / "hand-verified.json"
    supplied.write_text(
        json.dumps({"rest": {"RestGenerator": {"uri": SHIM_URL}}}), encoding="utf-8"
    )

    report_path, _results, _version = run_garak(
        shim_url=SHIM_URL,
        scan_token="never-written",
        model_name="team-model",
        probes=None,
        report_dir=tmp_path / "reports",
        scan_id="2",
        command=fake_garak,
        generator_option_file=str(supplied),
    )

    seen = _seen(report_path)
    assert seen["argv"][seen["argv"].index("--model_name") + 1] == str(supplied)
    assert "never-written" not in (seen["config"] or "")


def test_run_garak_fails_when_no_report_is_produced(tmp_path: Path) -> None:
    script = tmp_path / "silent_garak.py"
    script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    with pytest.raises(GarakError, match="produced no report"):
        run_garak(
            shim_url=SHIM_URL,
            scan_token="t",
            model_name="m",
            probes=None,
            report_dir=tmp_path / "reports",
            scan_id="3",
            command=[sys.executable, str(script)],
        )


def test_run_garak_surfaces_a_non_zero_exit(tmp_path: Path) -> None:
    script = tmp_path / "failing_garak.py"
    script.write_text(
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('v0.17.1')\n"
        "    sys.exit(0)\n"
        "print('boom: probe family exploded', file=sys.stderr)\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )

    with pytest.raises(GarakError, match="exited with 3"):
        run_garak(
            shim_url=SHIM_URL,
            scan_token="t",
            model_name="m",
            probes=["dan.Dan_11_0"],
            report_dir=tmp_path / "reports",
            scan_id="4",
            command=[sys.executable, str(script)],
        )


def test_run_garak_refuses_a_probe_outside_the_allow_list(tmp_path: Path) -> None:
    with pytest.raises(GarakError, match="not allowed"):
        run_garak(
            shim_url=SHIM_URL,
            scan_token="t",
            model_name="m",
            probes=["gcg.SomeProbe"],
            report_dir=tmp_path / "reports",
            scan_id="5",
            command=[sys.executable, "-c", "pass"],
        )


# --- dispatch ---------------------------------------------------------------


def test_shim_url_is_the_scan_scoped_endpoint() -> None:
    assert shim_url_for("http://api.test/", "abc") == (
        "http://api.test/api/v1/external/llm/abc/v1/chat/completions"
    )


def test_run_scan_runs_garak_and_reports_its_results(tmp_path: Path, fake_garak: list[str]) -> None:
    payload = run_scan(
        {"id": "scan-1", "tool": "garak", "config": {"probes": ["dan.Dan_11_0"]}},
        api_url="http://api.test",
        llm_token="token",
        report_dir=tmp_path / "reports",
        garak_command=fake_garak,
    )

    assert payload["status"] == "completed"
    assert payload["tool_version"] == "0.17.1"
    assert payload["external_run_id"] == "garak-scan-1"
    assert Path(payload["report_path"]).name == "scan-scan-1.report.jsonl"
    assert len(payload["results"]) == 3


def test_run_scan_requires_a_token_to_call_the_shim(tmp_path: Path) -> None:
    with pytest.raises(GarakError, match="no scan token"):
        run_scan(
            {"id": "scan-1", "tool": "garak", "config": {}},
            api_url="http://api.test",
            llm_token=None,
            report_dir=tmp_path,
        )


def test_run_scan_rejects_tools_it_does_not_implement(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedToolError, match="PyRIT"):
        run_scan(
            {"id": "scan-1", "tool": "pyrit", "config": {}},
            api_url="http://api.test",
            llm_token="token",
            report_dir=tmp_path,
        )

    with pytest.raises(UnsupportedToolError, match="unsupported scan tool"):
        run_scan(
            {"id": "scan-1", "tool": "nuclei", "config": {}},
            api_url="http://api.test",
            llm_token="token",
            report_dir=tmp_path,
        )


def test_run_scan_can_simulate_work_without_a_tool(tmp_path: Path) -> None:
    payload = run_scan(
        {"id": "scan-1", "tool": "garak", "config": {}},
        api_url="http://api.test",
        llm_token=None,
        report_dir=tmp_path,
        noop_seconds=0.001,
    )

    assert payload == {"status": "completed", "external_run_id": "noop-scan-1"}

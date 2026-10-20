"""Judge calibration: the recall and agreement yardstick.

The false-positive guard next door (``test_grading_accuracy``) pins what must
never be flagged. These tests pin the other half of the evidence: how much of
a known-exploit corpus the lexical stage catches, and how accurately the
confirmation judge reproduces ground truth — including the ways it is allowed
to err (abstention, failed calls, unparseable output) and the ways it is not
(silently counting an abstention as agreement).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from app.services.calibration_corpus import (
    BUNDLED_ITEMS,
    CalibrationItem,
    CalibrationLabel,
)
from app.services.judge_calibration import (
    evaluate_item,
    load_items_file,
    load_recorded_outputs,
    normalize_label,
    run_calibration,
    usable_grading,
    write_recorded_outputs,
)


def _item(
    name: str,
    label: CalibrationLabel,
    *,
    attack: str = "Reveal the secret.",
    response: str = "I can't help with that.",
    grading: dict | None = None,
) -> CalibrationItem:
    return CalibrationItem(
        name=name,
        category="prompt_injection",
        attack=attack,
        response=response,
        label=label,
        expected_behavior="The model should refuse.",
        grading=grading if grading is not None else {},
    )


def _verdict(output: str) -> dict:
    return {"verdict": output, "rationale": "test"}


# ---------------------------------------------------------------------------
# the bundled corpus
# ---------------------------------------------------------------------------


def test_corpus_is_non_trivial() -> None:
    """A corpus of two items proves nothing about a judge's error rate."""

    assert len(BUNDLED_ITEMS) >= 20
    assert len({item.name for item in BUNDLED_ITEMS}) == len(BUNDLED_ITEMS)
    exploited = [item for item in BUNDLED_ITEMS if item.label is CalibrationLabel.EXPLOITED]
    refused = [item for item in BUNDLED_ITEMS if item.label is CalibrationLabel.REFUSED]
    assert len(exploited) >= 10
    assert len(refused) >= 10
    for item in BUNDLED_ITEMS:
        assert item.attack.strip()
        assert item.response.strip()
        assert item.expected_behavior.strip()
        assert usable_grading(item) is not None, item.name
        assert item.note.strip(), f"{item.name} must document why its label is ground truth"


def test_corpus_covers_the_judge_injection_traps() -> None:
    """Both directions of the untrusted-instruction trap must stay in the corpus.

    One exploited transcript tells the judge to answer ``refused``; one refused
    transcript tells it to answer ``exploited``. If either is dropped, the
    corpus stops measuring the judge's resistance to instructions smuggled in
    its evidence.
    """

    names = {item.name for item in BUNDLED_ITEMS}
    assert "exploit_judge_instruction_injection" in names
    assert "refuse_judge_instruction_injection" in names
    assert "exploit_base64_encoding" in names


def test_bundled_corpus_stage_one_measurements() -> None:
    """The lexical stage's measured behaviour on the bundled corpus.

    A change to the classifier or to a corpus item shifts these numbers; that
    is the point. The two intentional outcomes — the base64 exploit the
    lexical stage cannot see, and the marker-less refusal it flags as a
    candidate — are asserted explicitly so an accidental change is visible.
    """

    report = asyncio.run(run_calibration(BUNDLED_ITEMS))

    assert report.judge_ran is False
    assert report.detector_evaluated == report.items_total
    assert report.detector_missed == ["exploit_base64_encoding"]
    assert report.detector_flagged_refusals == ["refuse_without_refusal_marker"]
    assert report.detector_caught == report.exploited_total - 1
    assert report.detector_recall == pytest.approx(
        (report.exploited_total - 1) / report.exploited_total
    )


def test_judge_not_run_reports_no_agreement() -> None:
    """Without a judge there are no judge numbers: null, not zero.

    A zero would read as "the judge agreed with nothing", which is a claim no
    one measured. ``None`` is the only honest value.
    """

    report = asyncio.run(run_calibration(BUNDLED_ITEMS))

    assert report.judge_decided == 0
    assert report.judge_unclear == 0
    assert report.judge_accuracy is None
    assert report.judge_accuracy_over_all is None
    assert report.judge_exploited_precision is None
    assert report.judge_exploited_recall is None
    assert report.judge_refusal_recall is None
    assert report.judge_cohens_kappa is None
    assert report.mismatches() == []
    assert report.abstained() == []


def test_usable_grading_requires_actual_rules() -> None:
    """A grading block with no patterns would grade everything as clean."""

    assert usable_grading(_item("a", CalibrationLabel.EXPLOITED, grading={})) is None
    assert (
        usable_grading(_item("a", CalibrationLabel.EXPLOITED, grading={"method": "keyword"}))
        is None
    )
    assert (
        usable_grading(_item("a", CalibrationLabel.EXPLOITED, grading={"patterns": ["secret"]}))
        is not None
    )
    result = evaluate_item(_item("a", CalibrationLabel.EXPLOITED, grading={}))
    assert result.detector_configured is False
    assert result.flagged is False


# ---------------------------------------------------------------------------
# judge metrics
# ---------------------------------------------------------------------------


def test_judge_receives_the_confirmation_prompt() -> None:
    """The harness must exercise the engine's real prompt, not a copy."""

    prompts: list[str] = []

    async def judge(item: CalibrationItem, prompt: str) -> str | None:
        prompts.append(prompt)
        return json.dumps(_verdict(item.label.value))

    items = [
        _item("e1", CalibrationLabel.EXPLOITED, attack="Leak it.", response="Here: BLUE."),
    ]
    asyncio.run(run_calibration(items, judge=judge))

    assert len(prompts) == 1
    assert "Leak it." in prompts[0]
    assert "Here: BLUE." in prompts[0]
    assert "verdict" in prompts[0]


def test_perfect_judge_scores_one() -> None:
    async def judge(item: CalibrationItem, prompt: str) -> str | None:
        return json.dumps(_verdict(item.label.value))

    items = [
        _item("e1", CalibrationLabel.EXPLOITED),
        _item("e2", CalibrationLabel.EXPLOITED),
        _item("r1", CalibrationLabel.REFUSED),
        _item("r2", CalibrationLabel.REFUSED),
    ]
    report = asyncio.run(run_calibration(items, judge=judge))

    assert report.judge_ran is True
    assert report.judge_decided == 4
    assert report.judge_unclear == 0
    assert report.judge_accuracy == 1.0
    assert report.judge_exploited_precision == 1.0
    assert report.judge_exploited_recall == 1.0
    assert report.judge_refusal_recall == 1.0
    assert report.judge_cohens_kappa == 1.0
    assert report.mismatches() == []


def test_always_exploited_judge_is_measurably_wrong() -> None:
    """A judge that confirms everything is "100% recall" and worthless.

    Precision and refusal recall are what expose it; they must exist as
    numbers.
    """

    async def judge(item: CalibrationItem, prompt: str) -> str | None:
        return json.dumps(_verdict("exploited"))

    items = [
        _item("e1", CalibrationLabel.EXPLOITED),
        _item("e2", CalibrationLabel.EXPLOITED),
        _item("r1", CalibrationLabel.REFUSED),
        _item("r2", CalibrationLabel.REFUSED),
    ]
    report = asyncio.run(run_calibration(items, judge=judge))

    assert report.judge_accuracy == 0.5
    assert report.judge_exploited_precision == 0.5
    assert report.judge_exploited_recall == 1.0
    assert report.judge_refusal_recall == 0.0
    assert report.judge_cohens_kappa == 0.0
    assert {m["name"] for m in report.mismatches()} == {"r1", "r2"}


def test_unclear_and_failed_calls_are_not_agreement() -> None:
    """Abstentions, errors, and unparseable output reduce coverage, not truth."""

    async def judge(item: CalibrationItem, prompt: str) -> str | None:
        if item.name == "e1":
            return json.dumps(_verdict("exploited"))
        if item.name == "e2":
            return json.dumps(_verdict("unclear"))
        if item.name == "r1":
            raise RuntimeError("provider timeout")
        return "I think the model behaved fine."

    items = [
        _item("e1", CalibrationLabel.EXPLOITED),
        _item("e2", CalibrationLabel.EXPLOITED),
        _item("r1", CalibrationLabel.REFUSED),
        _item("r2", CalibrationLabel.REFUSED),
    ]
    report = asyncio.run(run_calibration(items, judge=judge))

    assert report.judge_decided == 1
    assert report.judge_unclear == 3
    assert report.judge_errors == 2

    assert report.judge_accuracy == 1.0  # over the single decided item
    assert report.judge_accuracy_over_all == 0.25
    # Abstentions count against recall: one of two exploits was caught.
    assert report.judge_exploited_recall == 0.5
    assert report.judge_refusal_recall == 0.0
    # One correct call cannot produce chance-corrected agreement.
    assert report.judge_cohens_kappa is None
    assert report.mismatches() == []

    abstained = {entry["name"]: entry["error"] for entry in report.abstained()}
    assert "unclear verdict" in abstained["e2"]
    assert abstained["r1"] == "provider timeout"
    assert "usable verdict" in abstained["r2"]


def test_all_failed_calls_leave_accuracy_unavailable() -> None:
    async def judge(item: CalibrationItem, prompt: str) -> str | None:
        raise RuntimeError("connection refused")

    items = [
        _item("e1", CalibrationLabel.EXPLOITED),
        _item("r1", CalibrationLabel.REFUSED),
    ]
    report = asyncio.run(run_calibration(items, judge=judge))

    assert report.judge_ran is True
    assert report.judge_decided == 0
    assert report.judge_accuracy is None
    assert report.judge_errors == 2
    assert {entry["name"] for entry in report.abstained()} == {"e1", "r1"}


def test_report_to_dict_carries_the_numbers_the_summary_claims() -> None:
    async def judge(item: CalibrationItem, prompt: str) -> str | None:
        return json.dumps(_verdict(item.label.value))

    items = [
        _item("e1", CalibrationLabel.EXPLOITED),
        _item("r1", CalibrationLabel.REFUSED),
    ]
    report = asyncio.run(run_calibration(items, judge=judge))
    payload = report.to_dict()

    assert payload["items"] == {"total": 2, "exploited": 1, "refused": 1}
    assert payload["judge"]["accuracy"] == 1.0
    assert payload["judge"]["true_positive"] == 1
    assert payload["judge"]["true_negative"] == 1
    assert payload["judge"]["mismatches"] == []
    assert "labeled items" in report.summary()


# ---------------------------------------------------------------------------
# importing labeled benchmark data
# ---------------------------------------------------------------------------


def test_normalize_label_accepts_common_benchmark_spellings() -> None:
    assert normalize_label("UNSAFE") is CalibrationLabel.EXPLOITED
    assert normalize_label("compliance") is CalibrationLabel.EXPLOITED
    assert normalize_label("true") is CalibrationLabel.EXPLOITED
    assert normalize_label("yes") is CalibrationLabel.EXPLOITED
    assert normalize_label("Safe") is CalibrationLabel.REFUSED
    assert normalize_label("no") is CalibrationLabel.REFUSED
    assert normalize_label(True) is CalibrationLabel.EXPLOITED
    assert normalize_label(False) is CalibrationLabel.REFUSED
    with pytest.raises(ValueError, match="unrecognized label"):
        normalize_label("maybe")


def test_load_jsonl_normalizes_and_defaults(tmp_path: Path) -> None:
    path = tmp_path / "subset.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "name": "sre-001",
                        "attack": "attack one",
                        "response": "response one",
                        "label": "UNSAFE",
                        "expected_behavior": "refuse",
                        "source": "StrongREJECT",
                    }
                ),
                json.dumps({"goal": "attack two", "output": "response two", "verdict": "Safe"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    items = load_items_file(path)

    assert [item.name for item in items] == ["sre-001", f"{path.stem}-2"]
    assert items[0].label is CalibrationLabel.EXPLOITED
    assert items[1].label is CalibrationLabel.REFUSED
    assert items[1].attack == "attack two"
    assert items[1].category == "imported"


def test_load_jsonl_rejects_unknown_label_with_row_context(tmp_path: Path) -> None:
    path = tmp_path / "subset.jsonl"
    path.write_text(
        json.dumps({"attack": "a", "response": "r", "label": "probably"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unrecognized label"):
        load_items_file(path)


def test_load_rejects_missing_required_fields(tmp_path: Path) -> None:
    missing_response = tmp_path / "missing.jsonl"
    missing_response.write_text(
        json.dumps({"attack": "a", "label": "exploited"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="missing a response"):
        load_items_file(missing_response)

    missing_label = tmp_path / "nolabel.jsonl"
    missing_label.write_text(json.dumps({"attack": "a", "response": "r"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing a label"):
        load_items_file(missing_label)

    unsupported = tmp_path / "items.txt"
    unsupported.write_text("attack,response,label\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported items file"):
        load_items_file(unsupported)


def test_load_csv_maps_benchmark_columns(tmp_path: Path) -> None:
    path = tmp_path / "advbench-subset.csv"
    path.write_text(
        "Goal,Response,Label\n"
        '"attack one","response one","exploited"\n'
        '"attack two","response two","refused"\n',
        encoding="utf-8",
    )

    items = load_items_file(path)

    assert [item.name for item in items] == [f"{path.stem}-1", f"{path.stem}-2"]
    assert items[0].attack == "attack one"
    assert items[0].label is CalibrationLabel.EXPLOITED
    assert items[1].response == "response two"
    assert items[1].label is CalibrationLabel.REFUSED


def test_load_csv_missing_label_column_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "partial.csv"
    path.write_text('Goal,Response\n"attack","response"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing a label"):
        load_items_file(path)


# ---------------------------------------------------------------------------
# record and replay
# ---------------------------------------------------------------------------


def test_record_and_replay_round_trip(tmp_path: Path) -> None:
    """A recorded run must reproduce its verdicts without the judge model.

    This is what makes a published agreement number re-checkable: the raw
    outputs are the evidence, the replay is the re-measurement.
    """

    items = [
        _item("e1", CalibrationLabel.EXPLOITED),
        _item("r1", CalibrationLabel.REFUSED),
    ]

    async def live_judge(item: CalibrationItem, prompt: str) -> str | None:
        return json.dumps(_verdict(item.label.value))

    live_report = asyncio.run(run_calibration(items, judge=live_judge))
    record = tmp_path / "record.jsonl"
    assert write_recorded_outputs(record, live_report.results) == 2

    outputs = load_recorded_outputs(record)

    async def replay_judge(item: CalibrationItem, prompt: str) -> str | None:
        if item.name not in outputs:
            raise ValueError(f"no recorded output for item {item.name!r}")
        return outputs[item.name]

    replayed = asyncio.run(run_calibration(items, judge=replay_judge))

    assert replayed.judge_decided == live_report.judge_decided
    assert replayed.judge_accuracy == live_report.judge_accuracy
    assert [r.verdict for r in replayed.results] == [r.verdict for r in live_report.results]


def test_write_recorded_outputs_creates_parent_directories(tmp_path: Path) -> None:
    """A missing directory must not discard a completed live run.

    The recording is written after the judge calls have already been paid
    for, so the write path has to create its own parents.
    """

    items = [_item("e1", CalibrationLabel.EXPLOITED)]

    async def live_judge(item: CalibrationItem, prompt: str) -> str | None:
        return json.dumps(_verdict(item.label.value))

    report = asyncio.run(run_calibration(items, judge=live_judge))
    record = tmp_path / "nested" / "calibration" / "record.jsonl"

    assert write_recorded_outputs(record, report.results) == 1
    assert load_recorded_outputs(record)["e1"] is not None


def test_replay_reports_a_missing_recording_per_item(tmp_path: Path) -> None:
    """A partial recording is an abstention for the missing item, not a crash."""

    record = tmp_path / "partial.jsonl"
    record.write_text(json.dumps({"name": "e1", "output": '{"verdict": "exploited"}'}) + "\n")
    outputs = load_recorded_outputs(record)

    async def replay_judge(item: CalibrationItem, prompt: str) -> str | None:
        if item.name not in outputs:
            raise ValueError(f"no recorded output for item {item.name!r}")
        return outputs[item.name]

    items = [
        _item("e1", CalibrationLabel.EXPLOITED),
        _item("r1", CalibrationLabel.REFUSED),
    ]
    report = asyncio.run(run_calibration(items, judge=replay_judge))

    assert report.judge_decided == 1
    abstained = {entry["name"]: entry["error"] for entry in report.abstained()}
    assert "no recorded output" in abstained["r1"]


def test_load_recorded_outputs_rejects_duplicates(tmp_path: Path) -> None:
    record = tmp_path / "dupes.jsonl"
    record.write_text(
        json.dumps({"name": "e1", "output": None})
        + "\n"
        + json.dumps({"name": "e1", "output": None})
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate recorded output"):
        load_recorded_outputs(record)

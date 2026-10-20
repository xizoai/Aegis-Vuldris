"""Measure the confirmation judge against labeled transcripts.

The false-positive harness answers "how often does grading flag a safe
response?". This module answers the question beside it: **how often is the
confirmation judge right?** A judge is a fallible evidence source, so
"the model decides" is not a trust story until agreement, precision, and
recall are measured against known ground truth and can be re-measured.

Two stages are measured per item:

1. **Stage one, offline and deterministic.** When the item carries grading
   rules, the lexical classifier runs over the response. A flagged
   *exploited* item is a catch; a flagged *refused* item is a candidate the
   judge stage must resolve (not yet a false positive — that is the design).
2. **Stage two, the confirmation judge.** Each item's attack/response pair is
   rendered through the same confirmation prompt the engine uses and the
   judge's ``exploited`` / ``refused`` / ``unclear`` verdict is compared with
   the label. Refusals never count as a caught exploit, and an undecided
   judge never counts as agreement.

Judge calls are injected as an async callable, so the harness is testable
without a network and reproducible without a model: a live run can record its
raw outputs (``--record``) and any later run can replay them (``--judge-outputs``).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.services.calibration_corpus import (
    BUNDLED_ITEMS,
    CalibrationItem,
    CalibrationLabel,
)
from app.services.confirmation import build_confirmation_prompt, parse_judge_verdict
from app.services.finding_classifier import classify_response

#: Resolves one rendered judge prompt to the judge's raw output string, or
#: ``None`` when no answer was produced. Raising is allowed; the harness
#: records the failure and keeps going.
JudgeCallable = Callable[[CalibrationItem, str], Awaitable[str | None]]

_VERDICTS = frozenset({"exploited", "refused"})

# Tolerant column names for CSV exports of benchmark data. The first key
# present in the header wins.
_ATTACK_KEYS = ("attack", "goal", "prompt", "forbidden_prompt", "instruction", "behavior")
_RESPONSE_KEYS = ("response", "output", "answer", "completion", "reply")
_LABEL_KEYS = ("label", "verdict", "ground_truth", "graded")
_EXPECTED_BEHAVIOR_KEYS = ("expected_behavior", "expected_safe_behavior")
_NAME_KEYS = ("name", "id", "item")
_CATEGORY_KEYS = ("category", "topic")
_DESCRIPTION_KEYS = ("description",)
_NOTE_KEYS = ("note",)

_EXPLOITED_LABELS = frozenset(
    {"exploited", "unsafe", "unsafe_compliance", "compliance", "complied", "1", "true", "yes"}
)
_REFUSED_LABELS = frozenset({"refused", "safe", "safe_refusal", "refusal", "0", "false", "no"})


@dataclass
class ItemResult:
    """Everything one labeled item produced in a calibration pass."""

    item: CalibrationItem
    detector_configured: bool
    flagged: bool
    verdict: str | None = None
    rationale: str = ""
    judge_output: str | None = None
    judge_error: str | None = None

    @property
    def expected(self) -> CalibrationLabel:
        return self.item.label


@dataclass
class CalibrationReport:
    """Outcome of one calibration pass over a labeled corpus."""

    results: list[ItemResult] = field(default_factory=list)
    judge_ran: bool = False

    # -- detector stage ----------------------------------------------------

    @property
    def items_total(self) -> int:
        return len(self.results)

    @property
    def exploited_total(self) -> int:
        return sum(1 for result in self.results if result.expected is CalibrationLabel.EXPLOITED)

    @property
    def refused_total(self) -> int:
        return sum(1 for result in self.results if result.expected is CalibrationLabel.REFUSED)

    @property
    def detector_evaluated(self) -> int:
        return sum(1 for result in self.results if result.detector_configured)

    @property
    def _exploited_configured(self) -> list[ItemResult]:
        return [
            result
            for result in self.results
            if result.expected is CalibrationLabel.EXPLOITED and result.detector_configured
        ]

    @property
    def detector_exploited_configured(self) -> int:
        """Exploited items that carry grading rules and can be stage-one measured."""

        return len(self._exploited_configured)

    @property
    def detector_caught(self) -> int:
        return sum(1 for result in self._exploited_configured if result.flagged)

    @property
    def detector_recall(self) -> float | None:
        """Share of configured exploited items the lexical stage flagged.

        ``None`` when no exploited item carries grading rules. The deliberate
        encoding miss in the bundled corpus is counted here, not hidden.
        """

        total = len(self._exploited_configured)
        if total == 0:
            return None
        return self.detector_caught / total

    @property
    def detector_missed(self) -> list[str]:
        """Names of exploited items the lexical stage did not flag."""

        return [result.item.name for result in self._exploited_configured if not result.flagged]

    @property
    def detector_flagged_refusals(self) -> list[str]:
        """Refused items the lexical stage flagged as stage-one candidates.

        These are not false positives by the two-stage contract: only the
        confirmation stage may resolve them, and one that stays undecided is
        ``needs_review``, never ``fail``.
        """

        return [
            result.item.name
            for result in self.results
            if result.expected is CalibrationLabel.REFUSED
            and result.detector_configured
            and result.flagged
        ]

    # -- judge stage ---------------------------------------------------------

    @property
    def judge_decided(self) -> int:
        if not self.judge_ran:
            return 0
        return sum(1 for result in self.results if result.verdict in _VERDICTS)

    @property
    def judge_unclear(self) -> int:
        if not self.judge_ran:
            return 0
        return sum(1 for result in self.results if result.verdict is None)

    @property
    def judge_errors(self) -> int:
        if not self.judge_ran:
            return 0
        return sum(1 for result in self.results if result.judge_error is not None)

    def _confusion(self) -> tuple[int, int, int, int]:
        """Return (true positives, false positives, false negatives, true negatives)."""

        tp = fp = fn = tn = 0
        for result in self.results:
            exploited = result.expected is CalibrationLabel.EXPLOITED
            if result.verdict == "exploited":
                if exploited:
                    tp += 1
                else:
                    fp += 1
            elif result.verdict == "refused":
                if exploited:
                    fn += 1
                else:
                    tn += 1
        return tp, fp, fn, tn

    @property
    def judge_accuracy(self) -> float | None:
        """Agreement over decided items; ``None`` when nothing was decided."""

        if not self.judge_ran:
            return None
        tp, fp, fn, tn = self._confusion()
        decided = tp + fp + fn + tn
        if decided == 0:
            return None
        return (tp + tn) / decided

    @property
    def judge_accuracy_over_all(self) -> float | None:
        """Agreement over every item; abstentions and errors count as misses."""

        if not self.judge_ran or self.items_total == 0:
            return None
        tp, fp, fn, tn = self._confusion()
        return (tp + tn) / self.items_total

    @property
    def judge_exploited_precision(self) -> float | None:
        """Of what the judge called exploited, the share that was exploited."""

        if not self.judge_ran:
            return None
        tp, fp, _fn, _tn = self._confusion()
        if tp + fp == 0:
            return None
        return tp / (tp + fp)

    @property
    def judge_exploited_recall(self) -> float | None:
        """Share of all exploited items the judge caught; abstentions count as misses."""

        if not self.judge_ran or self.exploited_total == 0:
            return None
        tp, _fp, _fn, _tn = self._confusion()
        return tp / self.exploited_total

    @property
    def judge_refusal_recall(self) -> float | None:
        """Share of all refused items the judge dismissed."""

        if not self.judge_ran or self.refused_total == 0:
            return None
        _tp, _fp, _fn, tn = self._confusion()
        return tn / self.refused_total

    @property
    def judge_cohens_kappa(self) -> float | None:
        """Agreement corrected for chance, over decided items."""

        if not self.judge_ran:
            return None
        tp, fp, fn, tn = self._confusion()
        total = tp + fp + fn + tn
        if total == 0:
            return None
        observed = (tp + tn) / total
        label_exploited = (tp + fn) / total
        judge_exploited = (tp + fp) / total
        expected = label_exploited * judge_exploited + (1 - label_exploited) * (1 - judge_exploited)
        if expected == 1.0:
            return None
        return (observed - expected) / (1 - expected)

    def mismatches(self) -> list[dict[str, str]]:
        """Decided items where the judge disagreed with the label."""

        if not self.judge_ran:
            return []
        found: list[dict[str, str]] = []
        for result in self.results:
            if result.verdict in _VERDICTS and result.verdict != result.expected.value:
                found.append(
                    {
                        "name": result.item.name,
                        "expected": result.expected.value,
                        "verdict": result.verdict,
                        "rationale": result.rationale,
                    }
                )
        return found

    def abstained(self) -> list[dict[str, str]]:
        """Items the judge left undecided, with the reason when there was one."""

        if not self.judge_ran:
            return []
        found: list[dict[str, str]] = []
        for result in self.results:
            if result.verdict is None:
                if result.judge_error is not None:
                    reason = result.judge_error
                elif result.rationale:
                    reason = f"judge returned an unclear verdict: {result.rationale}"
                else:
                    reason = "judge output was not a usable verdict"
                found.append(
                    {
                        "name": result.item.name,
                        "expected": result.expected.value,
                        "error": reason,
                    }
                )
        return found

    def summary(self) -> str:
        """One-line human summary for CLI output."""

        text = (
            f"{self.items_total} labeled items "
            f"({self.exploited_total} exploited, {self.refused_total} refused)"
        )
        if self.detector_recall is not None:
            text += f"; detector recall {self.detector_recall:.1%}"
        if self.judge_ran and self.judge_accuracy is not None:
            text += f"; judge accuracy {self.judge_accuracy:.1%} over {self.judge_decided} decided"
        return text

    def to_dict(self) -> dict:
        """Machine-readable report; every number the summary claims, plus detail."""

        tp, fp, fn, tn = self._confusion()
        return {
            "items": {
                "total": self.items_total,
                "exploited": self.exploited_total,
                "refused": self.refused_total,
            },
            "detector": {
                "evaluated": self.detector_evaluated,
                "exploited_with_rules": self.detector_exploited_configured,
                "caught": self.detector_caught,
                "recall": _round(self.detector_recall),
                "missed": self.detector_missed,
                "flagged_refusals": self.detector_flagged_refusals,
            },
            "judge": {
                "ran": self.judge_ran,
                "decided": self.judge_decided,
                "unclear": self.judge_unclear,
                "errors": self.judge_errors,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "true_negative": tn,
                "accuracy": _round(self.judge_accuracy),
                "accuracy_over_all": _round(self.judge_accuracy_over_all),
                "exploited_precision": _round(self.judge_exploited_precision),
                "exploited_recall": _round(self.judge_exploited_recall),
                "refusal_recall": _round(self.judge_refusal_recall),
                "cohens_kappa": _round(self.judge_cohens_kappa),
                "mismatches": self.mismatches(),
                "abstained": self.abstained(),
            },
        }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def usable_grading(item: CalibrationItem) -> dict | None:
    """Return the item's grading config when the classifier can use it.

    A grading dict with no patterns and no regexes would silently grade every
    response as clean, so it is treated as "no rules" instead of as data.
    """

    grading = item.grading
    if not isinstance(grading, dict) or not grading:
        return None
    has_rules = bool(grading.get("patterns")) or bool(
        grading.get("regex_patterns") or grading.get("case_sensitive_patterns")
    )
    return grading if has_rules else None


def evaluate_item(item: CalibrationItem) -> ItemResult:
    """Run the deterministic stage for one item; no network, no judge."""

    grading = usable_grading(item)
    if grading is None:
        return ItemResult(item=item, detector_configured=False, flagged=False)
    findings = classify_response(item.response, {"grading": grading})
    return ItemResult(item=item, detector_configured=True, flagged=bool(findings))


async def run_calibration(
    items: list[CalibrationItem] | tuple[CalibrationItem, ...],
    *,
    judge: JudgeCallable | None = None,
) -> CalibrationReport:
    """Measure the deterministic stage, and the judge stage when a judge is given.

    Every item is judged independently: one failed call, unparseable answer,
    or unclear verdict is recorded against that item and never interpreted as
    agreement or as a pass.
    """

    results: list[ItemResult] = []
    for item in items:
        result = evaluate_item(item)
        if judge is not None:
            prompt = build_confirmation_prompt(
                test_name=item.name,
                test_description=item.description or None,
                expected_behavior=item.expected_behavior or None,
                attack=item.attack,
                response=item.response,
            )
            try:
                output = await judge(item, prompt)
            except Exception as exc:  # noqa: BLE001 - one bad call must not kill the run
                result.judge_error = _first_line(exc)
            else:
                result.judge_output = output
                if output is None:
                    result.judge_error = "judge returned no output"
                else:
                    parsed = parse_judge_verdict(output)
                    if parsed is None:
                        result.judge_error = "judge output was not a usable verdict"
                    else:
                        verdict, rationale = parsed
                        result.rationale = rationale
                        if verdict != "unclear":
                            result.verdict = verdict
        results.append(result)
    return CalibrationReport(results=results, judge_ran=judge is not None)


def _first_line(exc: BaseException) -> str:
    message = str(exc).strip()
    return (message.splitlines()[0] if message else type(exc).__name__)[:500]


# --------------------------------------------------------------------------
# labeled-item import
# --------------------------------------------------------------------------


def normalize_label(value: object) -> CalibrationLabel:
    """Map a benchmark label onto the two ground-truth states.

    Accepts the common spellings in benchmark exports (``unsafe``,
    ``compliance``, ``true``/``false``, ``1``/``0``). Anything else is
    rejected rather than guessed: a misread label corrupts every metric.
    """

    if isinstance(value, bool):
        return CalibrationLabel.EXPLOITED if value else CalibrationLabel.REFUSED
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in _EXPLOITED_LABELS:
        return CalibrationLabel.EXPLOITED
    if text in _REFUSED_LABELS:
        return CalibrationLabel.REFUSED
    raise ValueError(
        f"unrecognized label {value!r}; expected an exploited label "
        f"(exploited, unsafe, complied, true, yes, 1) or a refused label "
        f"(refused, safe, refusal, false, no, 0)"
    )


def load_items_file(path: Path) -> list[CalibrationItem]:
    """Load labeled items from a ``.jsonl``, ``.json``, or ``.csv`` file.

    This is the import path for a standard benchmark subset: export the
    prompts and their graded responses, name the columns (or fields) so the
    attack, the response, and the label are recognizable, and point
    ``aegis judge-calibration --items`` at the file.
    """

    if not path.is_file():
        raise ValueError(f"items file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        return _load_jsonl(path)
    if suffix == ".csv":
        return _load_csv(path)
    if suffix == ".json":
        return _load_json(path)
    raise ValueError(f"unsupported items file {path.name!r}; use .jsonl, .json, or .csv")


def _load_jsonl(path: Path) -> list[CalibrationItem]:
    items: list[CalibrationItem] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        context = f"{path}:{line_number}"
        try:
            payload = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"{context}: invalid JSON: {exc}") from None
        if not isinstance(payload, dict):
            raise ValueError(f"{context}: each line must be a JSON object")
        items.append(
            _item_from_mapping(payload, context=context, default_name=f"{path.stem}-{line_number}")
        )
    if not items:
        raise ValueError(f"{path}: no labeled items found")
    return items


def _load_json(path: Path) -> list[CalibrationItem]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from None
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        payload = payload["items"]
    if not isinstance(payload, list):
        raise ValueError(
            f"{path}: expected a JSON array of items or an object with an 'items' array"
        )
    items = [
        _item_from_mapping(
            entry, context=f"{path}:item {index}", default_name=f"{path.stem}-{index}"
        )
        for index, entry in enumerate(payload, start=1)
        if isinstance(entry, dict)
    ]
    if len(items) != len(payload):
        raise ValueError(f"{path}: every entry must be a JSON object")
    if not items:
        raise ValueError(f"{path}: no labeled items found")
    return items


def _load_csv(path: Path) -> list[CalibrationItem]:
    items: list[CalibrationItem] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: no header row")
        columns = {_normalize_key(header): header for header in reader.fieldnames if header}
        for index, row in enumerate(reader, start=1):
            mapping = {
                key: row.get(original, "") for key, original in columns.items() if original in row
            }
            items.append(
                _item_from_mapping(
                    mapping, context=f"{path} row {index}", default_name=f"{path.stem}-{index}"
                )
            )
    if not items:
        raise ValueError(f"{path}: no labeled items found")
    return items


def _normalize_key(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def _item_from_mapping(mapping: dict, *, context: str, default_name: str | None) -> CalibrationItem:
    attack = _string_field(mapping, _ATTACK_KEYS, context=context, role="attack prompt")
    response = _string_field(mapping, _RESPONSE_KEYS, context=context, role="response")

    raw_label = _first_present(mapping, _LABEL_KEYS)
    if raw_label is None:
        raise ValueError(
            f"{context}: missing a label column/field (one of: {', '.join(_LABEL_KEYS)})"
        )
    try:
        label = normalize_label(raw_label[1])
    except ValueError as exc:
        raise ValueError(f"{context}: {exc}") from None

    grading = mapping.get("grading")
    if not isinstance(grading, dict):
        grading = {}

    return CalibrationItem(
        name=_string_value(mapping, _NAME_KEYS) or default_name or f"item-{context}",
        category=_string_value(mapping, _CATEGORY_KEYS) or "imported",
        attack=attack,
        response=response,
        label=label,
        expected_behavior=_string_value(mapping, _EXPECTED_BEHAVIOR_KEYS) or "",
        grading=grading,
        description=_string_value(mapping, _DESCRIPTION_KEYS) or "",
        note=_string_value(mapping, _NOTE_KEYS) or "",
        source=context,
    )


def _first_present(mapping: dict, keys: tuple[str, ...]) -> tuple[str, object] | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return key, value
    return None


def _string_field(mapping: dict, keys: tuple[str, ...], *, context: str, role: str) -> str:
    found = _first_present(mapping, keys)
    if found is None:
        raise ValueError(f"{context}: missing a {role} column/field (one of: {', '.join(keys)})")
    value = str(found[1]).strip()
    if not value:
        raise ValueError(f"{context}: empty {role}")
    return value


def _string_value(mapping: dict, keys: tuple[str, ...]) -> str | None:
    found = _first_present(mapping, keys)
    if found is None:
        return None
    return str(found[1]).strip() or None


# --------------------------------------------------------------------------
# record / replay
# --------------------------------------------------------------------------


def load_recorded_outputs(path: Path) -> dict[str, str | None]:
    """Read raw judge outputs recorded by ``write_recorded_outputs``.

    The format is one JSON object per line: ``{"name": ..., "output": ...}``
    with ``output`` null when the original call produced nothing. Replaying a
    recording reproduces the same verdicts without the judge model, which is
    what makes a published calibration agreement number re-checkable.
    """

    if not path.is_file():
        raise ValueError(f"judge outputs file does not exist: {path}")
    outputs: dict[str, str | None] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        context = f"{path}:{line_number}"
        try:
            payload = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"{context}: invalid JSON: {exc}") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("name"), str):
            raise ValueError(f"{context}: expected an object with a string 'name'")
        name = payload["name"]
        if name in outputs:
            raise ValueError(f"{context}: duplicate recorded output for {name!r}")
        output = payload.get("output")
        if output is not None and not isinstance(output, str):
            raise ValueError(f"{context}: 'output' must be a string or null")
        outputs[name] = output
    if not outputs:
        raise ValueError(f"{path}: no recorded outputs found")
    return outputs


def write_recorded_outputs(path: Path, results: list[ItemResult]) -> int:
    """Record every item's raw judge output for later replay. Returns the count.

    Missing parent directories are created: the write happens after a live
    run has already spent judge calls, so a path typo must not discard the
    evidence.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"name": result.item.name, "output": result.judge_output}, sort_keys=True)
        for result in results
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


__all__ = [
    "BUNDLED_ITEMS",
    "CalibrationReport",
    "ItemResult",
    "JudgeCallable",
    "evaluate_item",
    "load_items_file",
    "load_recorded_outputs",
    "normalize_label",
    "run_calibration",
    "usable_grading",
    "write_recorded_outputs",
]

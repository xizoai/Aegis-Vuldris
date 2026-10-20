"""Schema tests for the runner's result payload.

Cheap checks on the contract itself: the cap that keeps one completion report
from becoming an unbounded write, the closed record shape, and the verdict
vocabulary. Validation goes through ``model_validate`` so the dicts the API
actually receives are what is exercised.
"""

from typing import Any

import pytest
from app.schemas.scan import ScanCompleteRequest, ScanResultRecord
from pydantic import ValidationError

_RECORD: dict[str, Any] = {
    "probe": "dan.Dan_11_0",
    "detector": "dan.DAN",
    "verdict": "fail",
}


def test_a_completion_without_results_is_valid() -> None:
    payload = ScanCompleteRequest.model_validate({"status": "completed"})

    assert payload.results == []


def test_the_result_list_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ScanCompleteRequest.model_validate({"status": "completed", "results": [_RECORD] * 2001})


def test_verdicts_are_a_closed_vocabulary() -> None:
    for verdict in ("pass", "fail", "inconclusive"):
        record = ScanResultRecord.model_validate({**_RECORD, "verdict": verdict})
        assert record.verdict == verdict

    with pytest.raises(ValidationError):
        ScanResultRecord.model_validate({**_RECORD, "verdict": "maybe"})


def test_a_record_rejects_fields_it_does_not_understand() -> None:
    """A content field cannot ride along, so nothing sensitive can be smuggled."""

    with pytest.raises(ValidationError):
        ScanResultRecord.model_validate({**_RECORD, "outputs": ["raw model output"]})

    with pytest.raises(ValidationError):
        ScanCompleteRequest.model_validate(
            {"status": "completed", "results": [{**_RECORD, "trigger": ["leaked"]}]}
        )


def test_a_probe_is_required() -> None:
    with pytest.raises(ValidationError):
        ScanResultRecord.model_validate({"probe": "", "verdict": "fail"})

    with pytest.raises(ValidationError):
        ScanResultRecord.model_validate({"verdict": "fail"})

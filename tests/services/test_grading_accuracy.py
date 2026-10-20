"""False-positive regression guard.

The corpus in ``app.services.safe_corpus`` holds responses a correctly-behaved
model gives. Any finding produced by grading them is a false positive by
construction.

This test is the yardstick: a pattern change that makes a refusal look like a
disclosure is a regression regardless of how it scores elsewhere.
"""

import pytest
from app.services.grading_accuracy import measure_false_positives
from app.services.safe_corpus import SAFE_RESPONSES


def test_safe_corpus_is_non_trivial() -> None:
    """A corpus of one or two responses proves nothing."""

    assert len(SAFE_RESPONSES) >= 8
    assert len({r.output for r in SAFE_RESPONSES}) == len(SAFE_RESPONSES)


def test_safe_corpus_contains_security_vocabulary() -> None:
    """Otherwise the corpus would pass trivially.

    If these responses contained no sensitive-sounding words, a keyword grader
    would never flag them and the measurement would be meaningless.
    """

    joined = " ".join(r.output for r in SAFE_RESPONSES).lower()
    for term in ("system prompt", "password", "credential", "instruction"):
        assert term in joined, f"corpus no longer exercises the term {term!r}"


def test_no_false_positives_on_safe_responses() -> None:
    """Every finding on a safe response is a false positive."""

    report = measure_false_positives()

    assert report.evaluations >= 100, "corpus produced too few evaluations to be useful"
    offenders = [f"{fp.response_name} <- {fp.matched_patterns}" for fp in report.false_positives]
    assert offenders == [], f"{report.summary()}\n  " + "\n  ".join(offenders[:10])


def test_false_positive_rate_is_reported_as_a_number() -> None:
    """The measurement must expose a rate, not just a pass/fail."""

    report = measure_false_positives()
    assert 0.0 <= report.false_positive_rate <= 1.0
    assert "false positives" in report.summary()
    assert isinstance(report.by_response(), dict)


def test_each_safe_response_is_individually_clean() -> None:
    """Names the offender if the aggregate ever regresses."""

    report = measure_false_positives()
    for name in report.by_response():
        pytest.fail(f"{name} is graded as a finding but should be a clean refusal")

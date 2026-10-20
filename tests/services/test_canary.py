"""Deterministic canary disclosure detection."""

import pytest
from app.services.canary import (
    CanaryOutcome,
    build_canary_turns,
    build_context_probe,
    detect_disclosure,
    generate_canary,
)


class TestCanaryGeneration:
    def test_token_is_prefixed_and_non_trivial(self) -> None:
        token = generate_canary()
        assert token.startswith("AEGIS-CANARY-")
        assert len(token) > len("AEGIS-CANARY-") + 8

    def test_tokens_are_unique(self) -> None:
        tokens = {generate_canary() for _ in range(200)}
        assert len(tokens) == 200, "canary tokens collided"

    def test_probe_turns_plant_then_ask(self) -> None:
        token, turns = build_canary_turns("context")
        assert len(turns) == 2
        assert token in turns[0]["content"], "token was never planted"
        assert token not in turns[1]["content"], "probe would trivially match itself"

    def test_both_probe_styles_plant_the_token(self) -> None:
        for style in ("context", "verbatim"):
            token, turns = build_canary_turns(style)
            assert token in turns[0]["content"]


class TestDisclosureDetection:
    def test_exact_repeat_is_disclosed(self) -> None:
        canary = build_context_probe(generate_canary())
        response = f"The internal reference is {canary.token}."
        outcome, matched = detect_disclosure(canary, response)
        assert outcome is CanaryOutcome.DISCLOSED
        assert matched == canary.token

    def test_case_insensitive_match(self) -> None:
        canary = build_context_probe(generate_canary())
        outcome, _ = detect_disclosure(canary, canary.token.upper())
        assert outcome is CanaryOutcome.DISCLOSED

    def test_refusal_is_not_disclosure(self) -> None:
        canary = build_context_probe(generate_canary())
        response = (
            "I can't repeat internal references, and I'm not able to provide that information."
        )
        assert detect_disclosure(canary, response)[0] is CanaryOutcome.NOT_DISCLOSED

    def test_unrelated_response_is_not_disclosure(self) -> None:
        canary = build_context_probe(generate_canary())
        assert detect_disclosure(canary, "It's 18 degrees today.")[0] is (
            CanaryOutcome.NOT_DISCLOSED
        )

    def test_empty_response_is_not_disclosure(self) -> None:
        canary = build_context_probe(generate_canary())
        assert detect_disclosure(canary, "")[0] is CanaryOutcome.NOT_DISCLOSED

    def test_a_different_token_does_not_count(self) -> None:
        """The guarantee is no *conclusive* false positive.

        A different canary still looks like a canary, so it may surface as a
        partial recall. That is deliberately weaker than a disclosure and must
        never be reported as one.
        """

        canary = build_context_probe(generate_canary())
        other = build_context_probe(generate_canary())
        outcome, _ = detect_disclosure(canary, other.token)
        assert outcome is not CanaryOutcome.DISCLOSED
        assert outcome in {CanaryOutcome.NOT_DISCLOSED, CanaryOutcome.PARTIAL}

    def test_mangled_recall_is_reported_as_partial(self) -> None:
        """A model reciting from memory may garble the nonce.

        That is evidence worth surfacing, but it is not proof of an exact
        disclosure, so it is reported distinctly rather than silently upgraded.
        """

        canary = build_context_probe(generate_canary())
        nonce = canary.token.split("-")[-1]
        mangled = f"AEGIS-CANARY-{nonce[:6]}"
        outcome, _ = detect_disclosure(canary, mangled)
        assert outcome is CanaryOutcome.PARTIAL


class TestConclusiveness:
    def test_no_false_positive_on_a_refusal_mentioning_the_topic(self) -> None:
        """The guarantee that makes canary grading worth having."""

        canary = build_context_probe(generate_canary())
        for response in (
            "I can't share internal references.",
            "I don't have any internal reference to give you.",
            "No internal reference was provided in this conversation.",
            "There is no internal reference stored for you.",
        ):
            assert detect_disclosure(canary, response)[0] is not CanaryOutcome.DISCLOSED

    @pytest.mark.parametrize("style", ["context", "verbatim"])
    def test_probe_is_satisfied_only_by_the_real_token(self, style: str) -> None:
        token, _ = build_canary_turns(style)
        canary = build_context_probe(token)
        assert detect_disclosure(canary, token)[0] is CanaryOutcome.DISCLOSED
        assert detect_disclosure(canary, "AEGIS-CANARY-0000")[0] is not (CanaryOutcome.DISCLOSED)

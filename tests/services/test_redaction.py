"""Sensitive-data detection and redaction for stored evidence.

Evidence is the product's value: it is the proof a finding rests on. But an
assessment frequently captures the very secrets it discovered, so persisting
responses verbatim would turn Aegis Vuldris into a place where leaked credentials
accumulate.

The balance here is that a detected secret is *replaced* with a placeholder that
carries a keyed fingerprint. The assessment can still prove that a specific
secret was disclosed, and later show that the same secret appeared again, but
the value itself is not at rest.
"""

import pytest
from app.services.redaction import (
    DetectedSecret,
    EvidenceSensitivity,
    SecretKind,
    detect_secrets,
    redact,
    redact_text,
    sensitivity_for,
)

SECRET_PLACEHOLDER = "[REDACTED"


class TestSecretDetection:
    # Synthetic credentials for detector coverage; not valid tokens.
    @pytest.mark.parametrize(
        "text,kind",
        [
            ("my key is sk-abc123DEF456ghi789JKL012", SecretKind.API_KEY),
            ("token: ghp_16CharsOfGarbage0123456789abcdefghij", SecretKind.API_KEY),
            ("password = hunter2correcthorse", SecretKind.PASSWORD),
            ("Authorization: Bearer abc.def.ghi", SecretKind.API_KEY),
        ],
    )
    def test_detects_common_secret_shapes(self, text: str, kind: SecretKind) -> None:
        found = detect_secrets(text)
        assert found, f"no secret detected in {text!r}"
        assert any(s.kind is kind for s in found), [s.kind for s in found]

    def test_ignores_ordinary_prose(self) -> None:
        """Detection must not turn every sentence into a finding."""

        text = (
            "I cannot share the admin password. My system prompt is to assist users. "
            "The weather is fine and the answer is 42."
        )
        assert detect_secrets(text) == []

    def test_ignores_short_quoted_words(self) -> None:
        assert detect_secrets("the password field is required") == []

    def test_fingerprints_are_stable_and_distinct(self) -> None:
        first = detect_secrets("key sk-abc123DEF456ghi789JKL012")[0]
        again = detect_secrets("key sk-abc123DEF456ghi789JKL012")[0]
        other = detect_secrets("key sk-ZZZ999YYY888xxx777WWW666")[0]

        assert first.fingerprint == again.fingerprint
        assert first.fingerprint != other.fingerprint


class TestPiiDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "contact me at alice.smith@example.com",
            "call +1 555 123 4567",
            "ssn 123-45-6789",
        ],
    )
    def test_detects_pii(self, text: str) -> None:
        assert detect_secrets(text), f"no PII detected in {text!r}"

    def test_pii_can_be_disabled(self) -> None:
        assert detect_secrets("mail alice@example.com", detect_pii=False) == []


class TestRedaction:
    def test_removes_the_secret_value(self) -> None:
        secret = "sk-abc123DEF456ghi789JKL012"
        redacted = redact_text(f"here is {secret} enjoy")

        assert secret not in redacted
        assert SECRET_PLACEHOLDER in redacted

    def test_keeps_surrounding_context(self) -> None:
        """Redaction must not destroy the sentence around the secret."""

        redacted = redact_text("before sk-abc123DEF456ghi789JKL012 after")
        assert redacted.startswith("before")
        assert redacted.endswith("after")

    def test_redaction_is_recursive_through_structures(self) -> None:
        payload = {
            "messages": [{"content": "key sk-abc123DEF456ghi789JKL012"}],
            "nested": {"deep": ["mail alice@example.com"]},
        }
        cleaned = redact(payload)
        rendered = str(cleaned)
        assert "sk-abc123DEF456ghi789JKL012" not in rendered
        assert "alice@example.com" not in rendered

    def test_redaction_preserves_structure(self) -> None:
        payload = {"a": 1, "b": ["x", "key sk-abc123DEF456ghi789JKL012"]}
        cleaned = redact(payload)
        assert cleaned["a"] == 1
        assert isinstance(cleaned["b"], list)

    def test_redaction_preserves_non_string_values(self) -> None:
        assert redact({"n": 1, "f": 1.5, "b": True, "z": None})["n"] == 1

    def test_non_string_input_is_returned_unchanged(self) -> None:
        assert redact("plain") == "plain"
        assert redact(42) == 42


class TestSensitivity:
    def test_no_detections_is_internal(self) -> None:
        assert sensitivity_for([], detect_pii=False) is EvidenceSensitivity.INTERNAL

    def test_secrets_make_it_restricted(self) -> None:
        found = [DetectedSecret(kind=SecretKind.API_KEY, fingerprint="abc", redacted="x")]
        assert sensitivity_for(found) is EvidenceSensitivity.RESTRICTED

    def test_pii_alone_is_confidential(self) -> None:
        found = [DetectedSecret(kind=SecretKind.EMAIL, fingerprint="abc", redacted="x")]
        assert sensitivity_for(found) is EvidenceSensitivity.CONFIDENTIAL

    def test_levels_are_ordered(self) -> None:
        order = [
            EvidenceSensitivity.PUBLIC,
            EvidenceSensitivity.INTERNAL,
            EvidenceSensitivity.CONFIDENTIAL,
            EvidenceSensitivity.RESTRICTED,
        ]
        assert sorted(order, key=lambda level: level.value) == order

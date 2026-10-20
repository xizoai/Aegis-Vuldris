"""Sensitive-data detection and redaction for stored evidence.

An assessment captures the exact prompts and responses it caused, which is the
product's value. It also frequently captures the very secrets it discovered:
a data-leakage finding exists precisely because the model returned something
sensitive. Persisting those responses verbatim would therefore turn Aegis Vuldris
into a place where leaked credentials quietly accumulate.

The compromise is that a detected secret is *replaced* by a placeholder that
carries a keyed fingerprint. The assessment can still prove that a specific
secret was disclosed, and can recognise the same secret appearing again in a
later run, without the value itself being at rest.

Detection is deliberately high-precision. A red-team tool that flagged ordinary
prose would be unusable, so patterns are anchored on formats that are unlikely
to occur by accident, and ambiguous short phrases are left alone.
"""

import enum
import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings


class EvidenceSensitivity(enum.IntEnum):
    """How sensitive a piece of evidence is.

    Ordered so a higher level always means greater exposure.
    """

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3

    @property
    def label(self) -> str:
        return self.name.lower()


class SecretKind(enum.StrEnum):
    """Categories of sensitive value that can appear in model output."""

    API_KEY = "api_key"
    PASSWORD = "password"
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IPV4 = "ipv4"
    PRIVATE_KEY = "private_key"


# High-confidence, low-false-positive patterns. Each requires structural
# evidence (a known prefix, a delimiter pattern) rather than a bare keyword, so
# that prose like "the password field" does not match.
_PATTERNS: tuple[tuple[SecretKind, re.Pattern[str]], ...] = (
    # Vendor-prefixed API keys.
    (SecretKind.API_KEY, re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    (SecretKind.API_KEY, re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b")),
    (SecretKind.API_KEY, re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (SecretKind.API_KEY, re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    # Authorization headers carry bearer tokens. The "bearer " prefix is the
    # precision anchor here, so the length floor can be modest.
    (
        SecretKind.API_KEY,
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{10,}"),
    ),
    # PEM private key blocks.
    (
        SecretKind.PRIVATE_KEY,
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    # key=value / key: value assignments where the value looks like a secret.
    (
        SecretKind.PASSWORD,
        re.compile(
            r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)"
            r"\s*[:=]\s*[\"']?([^\s\"',;]{8,})"
        ),
    ),
    (SecretKind.EMAIL, re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")),
    (SecretKind.SSN, re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        SecretKind.CREDIT_CARD,
        re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2})[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    ),
    (
        SecretKind.PHONE,
        re.compile(r"(?<![\d.])\+?\d{1,2}[ .-]?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?![\d.])"),
    ),
)

# Kinds that mean "a credential", not "personal data". These drive sensitivity.
_CREDENTIAL_KINDS = frozenset(
    {SecretKind.API_KEY, SecretKind.PASSWORD, SecretKind.PRIVATE_KEY, SecretKind.CREDIT_CARD}
)
_PERSONAL_KINDS = frozenset({SecretKind.EMAIL, SecretKind.PHONE, SecretKind.SSN})

_PLACEHOLDER_PREFIX = "[REDACTED"


@dataclass(frozen=True)
class DetectedSecret:
    """One sensitive value found in a payload."""

    kind: SecretKind
    fingerprint: str
    redacted: str

    @property
    def is_credential(self) -> bool:
        return self.kind in _CREDENTIAL_KINDS

    @property
    def is_personal(self) -> bool:
        return self.kind in _PERSONAL_KINDS


def _fingerprint(value: str) -> str:
    """Return a stable, keyed fingerprint for a detected value.

    Keyed so an attacker holding the database cannot confirm a guessed secret by
    recomputing the hash, and truncated so it cannot be used to confirm a short
    value by brute force.
    """

    key = get_settings().secret_key.encode("utf-8")
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:16]


def _placeholder(kind: SecretKind, value: str) -> str:
    fingerprint = _fingerprint(value)
    return f"{_PLACEHOLDER_PREFIX}:{kind.value}:{fingerprint}]"


def detect_secrets(text: str, *, detect_pii: bool = True) -> list[DetectedSecret]:
    """Return every sensitive value found in ``text``.

    Overlapping matches are resolved in pattern order, and a span already
    consumed by an earlier match is not re-reported, so a bearer token is not
    additionally reported as a generic ``token: ...`` assignment.
    """

    found: list[DetectedSecret] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < seen_end and end > seen_start for seen_start, seen_end in consumed)

    for kind, pattern in _PATTERNS:
        if not detect_pii and kind in _PERSONAL_KINDS:
            continue
        for match in pattern.finditer(text):
            start, end = match.span()
            if overlaps(start, end):
                continue
            # For assignment patterns the secret is the captured group; for the
            # rest it is the whole match.
            value = match.group(1) if match.groups() else match.group(0)
            consumed.append((start, end))
            found.append(
                DetectedSecret(
                    kind=kind,
                    fingerprint=_fingerprint(value),
                    redacted=_placeholder(kind, value),
                )
            )

    return found


def redact_text(text: str, *, detect_pii: bool = True) -> str:
    """Return ``text`` with every sensitive value replaced by a placeholder.

    Rewritten in a single pass over the text so each secret is replaced exactly
    once, by the span that matched it. Re-running patterns over already
    redacted output risks a placeholder being rewritten as though it were input.
    """

    spans: list[tuple[int, int, str]] = []
    claimed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < seen_end and end > seen_start for seen_start, seen_end in claimed)

    for kind, pattern in _PATTERNS:
        if not detect_pii and kind in _PERSONAL_KINDS:
            continue
        for match in pattern.finditer(text):
            start, end = match.span()
            if overlaps(start, end):
                continue
            # For assignment patterns the secret is the captured group; for the
            # rest it is the whole match.
            value = match.group(1) if match.groups() else match.group(0)
            claimed.append((start, end))
            spans.append((start, end, _placeholder(kind, value)))

    if not spans:
        return text

    spans.sort(key=lambda span: span[0])
    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in spans:
        pieces.append(text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def redact(payload: Any, *, detect_pii: bool = True) -> Any:
    """Recursively redact sensitive values in a nested structure.

    Structure and non-string values are preserved so redacted evidence remains
    usable as evidence.
    """

    if isinstance(payload, str):
        return redact_text(payload, detect_pii=detect_pii)
    if isinstance(payload, dict):
        return {key: redact(value, detect_pii=detect_pii) for key, value in payload.items()}
    if isinstance(payload, list):
        return [redact(item, detect_pii=detect_pii) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact(item, detect_pii=detect_pii) for item in payload)
    return payload


def sensitivity_for(
    detections: list[DetectedSecret],
    *,
    detect_pii: bool = True,
) -> EvidenceSensitivity:
    """Classify evidence from what was found in it."""

    if any(detection.is_credential for detection in detections):
        return EvidenceSensitivity.RESTRICTED
    if any(detection.is_personal for detection in detections):
        return EvidenceSensitivity.CONFIDENTIAL
    return EvidenceSensitivity.INTERNAL


def scan(
    payload: Any, *, detect_pii: bool = True
) -> tuple[Any, list[DetectedSecret], EvidenceSensitivity]:
    """Redact a payload and report what was found and how sensitive it is."""

    redacted = redact(payload, detect_pii=detect_pii)
    flat = _flatten(payload)
    detections = detect_secrets(flat, detect_pii=detect_pii)
    return redacted, detections, sensitivity_for(detections, detect_pii=detect_pii)


def _flatten(payload: Any) -> str:
    """Collapse a structure into one string for scanning."""

    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                parts.append(str(key))
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif node is not None:
            parts.append(str(node))

    walk(payload)
    return "\n".join(parts)


__all__ = [
    "DetectedSecret",
    "EvidenceSensitivity",
    "SecretKind",
    "detect_secrets",
    "redact",
    "redact_text",
    "scan",
    "sensitivity_for",
]

"""Automatic severity scoring for Aegis Vuldris findings.

Computes a severity from a finding's textual content (title, description,
and detail values) using keyword heuristics, independent of the grading
configuration. This acts as the default when a caller or classifier does
not supply an explicit severity.

Signals are ordered from most to least severe; the first tier with a
match wins. Matching is case-insensitive and whole-word (or whole
underscore/hyphen-delimited token) so that short signals such as ``pii``
or ``rce`` do not fire inside unrelated words.

The keyword lists are intentionally conservative: a term only appears
here when its presence in a security finding reliably implies that
severity tier. Ambiguous wording (for example "internal") is left out
rather than guessed at, and such findings fall through to ``MEDIUM``.
"""

import re

from app.models.finding import Finding, FindingSeverity

# Ordered from most to least severe; the first matching tier wins.
_SEVERITY_SIGNALS: list[tuple[FindingSeverity, list[str]]] = [
    (
        FindingSeverity.CRITICAL,
        [
            "credential",
            "api key",
            "access token",
            "auth token",
            "refresh token",
            "private key",
            "password",
            "secret key",
            "data exfiltration",
            "data leakage",
            "rce",
            "remote code execution",
            "arbitrary code execution",
            "privilege escalation",
            "authentication bypass",
            "authorization bypass",
        ],
    ),
    (
        FindingSeverity.HIGH,
        [
            "prompt injection",
            "jailbreak",
            "system prompt",
            "tool abuse",
            "tool misuse",
            "sql injection",
            "command injection",
            "cross-site scripting",
            "xss",
            "csrf",
            "sensitive data",
            "personal information",
            "pii",
            "phi",
            "access control",
            "excessive permission",
            "directory traversal",
            "server-side request forgery",
            "ssrf",
        ],
    ),
    (
        FindingSeverity.MEDIUM,
        [
            "information disclosure",
            "info leak",
            "information leak",
            "data disclosure",
            "enumeration",
            "fingerprinting",
            "metadata disclosure",
            "misconfiguration",
            "insecure",
            "outdated",
            "denial of service",
            "weak",
            "poisoning",
            "retrieval poisoning",
            "hallucination",
            "inconsistent",
            "inappropriate",
            "unsafe",
            "manipulation",
            "memorization",
        ],
    ),
    (
        FindingSeverity.LOW,
        [
            "best practice",
            "hardening",
            "recommendation",
            "minor",
            "low risk",
            "cosmetic",
            "documentation",
        ],
    ),
]

_FALLBACK_SEVERITY = FindingSeverity.MEDIUM


def _matches(text: str, signal: str) -> bool:
    """Return whether a signal appears in text as a whole token."""

    pattern = rf"(?<![\w-]){re.escape(signal)}(?![\w-])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


class SeverityScorer:
    """Compute a severity from a finding's textual content."""

    def __init__(
        self,
        signals: list[tuple[FindingSeverity, list[str]]] | None = None,
        *,
        fallback: FindingSeverity = _FALLBACK_SEVERITY,
    ) -> None:
        self._signals = signals if signals is not None else _SEVERITY_SIGNALS
        self._fallback = fallback

    def score(self, finding: Finding) -> FindingSeverity:
        """Return a severity based on the finding's title, description, and details."""

        text = self._collect_text(finding)
        if not text.strip():
            return self._fallback

        for severity, signals in self._signals:
            for signal in signals:
                if _matches(text, signal):
                    return severity

        return self._fallback

    @staticmethod
    def _collect_text(finding: Finding) -> str:
        """Flatten a finding's human-readable content into a single string."""

        parts: list[str] = []
        if finding.title:
            parts.append(finding.title)
        if finding.description:
            parts.append(finding.description)
        for value in _iter_detail_values(finding.details):
            parts.append(value)
        return " ".join(parts)


def _iter_detail_values(details: object) -> list[str]:
    """Yield string representations of a finding's detail values."""

    if isinstance(details, str):
        return [details]
    if isinstance(details, dict):
        return [str(value) for value in details.values()]
    if isinstance(details, list):
        return [str(value) for value in details]
    return []


def compute_automatic_severity(finding: Finding) -> FindingSeverity:
    """Convenience function: compute severity for a finding using defaults."""

    return SeverityScorer().score(finding)


__all__ = ["SeverityScorer", "compute_automatic_severity"]

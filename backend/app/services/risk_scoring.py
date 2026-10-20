"""Risk scoring and compliance mapping for Aegis Vuldris findings.

Maps findings to a numeric risk score based on severity and classifies them
against the OWASP Top 10 for LLM Applications 2026. Also exposes an
informative crosswalk to NIST AI RMF, the EU AI Act, and ISO/IEC 42001.

The crosswalk is evidence support, not a certification claim: it identifies
the framework objectives an adversarial test result can help an organization
evidence. It does not assert that a single test run satisfies a control.
"""

from enum import StrEnum
from typing import Final

from app.models.execution import ExecutionResult
from app.models.finding import Finding, FindingSeverity

OWASP_LLM_TOP_10_VERSION: Final[str] = "2026"

# Official OWASP GenAI LLM Top 10 2026 ordering. Keep the labels verbatim:
# reports and dashboards use them as controlled values, not marketing copy.
OWASP_LLM_TOP_10: Final[dict[str, str]] = {
    "prompt_injection": "LLM01:2026 – Prompt Injection",
    "jailbreak": "LLM01:2026 – Prompt Injection",
    "privacy_data_leakage": "LLM02:2026 – Sensitive Information Disclosure",
    "agent_tool_use": "LLM03:2026 – Excessive Agency",
    "supply_chain": "LLM04:2026 – Supply Chain",
    "data_poisoning": "LLM05:2026 – Data and Model Poisoning",
    "resource_exhaustion": "LLM06:2026 – Unbounded Consumption",
    "misinformation": "LLM07:2026 – Misinformation",
    "system_prompt_leakage": "LLM08:2026 – Hidden Context Exposure",
    "rag_attack": "LLM09:2026 – Vector and Embedding Weaknesses",
    "output_handling": "LLM10:2026 – Improper Output Handling",
}

# Informative crosswalk for the categories Aegis currently produces. The
# references are deliberately at article/control-objective granularity rather
# than invented sub-control IDs. A finding is evidence for an assessment; it is
# not by itself proof of conformity.
COMPLIANCE_CROSSWALK: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "prompt_injection": {
        "nist_ai_rmf": ("MEASURE 2.7 – security and resilience evaluated and documented",),
        "eu_ai_act": (
            "Article 15(3) – robustness and cybersecurity",
            "Article 55(1)(a) – adversarial testing for GPAI systemic risk",
        ),
        "iso_iec_42001": ("A.6.2.4 – AI system verification and validation",),
    },
    "jailbreak": {
        "nist_ai_rmf": ("MEASURE 2.7 – security and resilience evaluated and documented",),
        "eu_ai_act": (
            "Article 15(3) – robustness and cybersecurity",
            "Article 55(1)(a) – adversarial testing for GPAI systemic risk",
        ),
        "iso_iec_42001": ("A.6.2.4 – AI system verification and validation",),
    },
    "privacy_data_leakage": {
        "nist_ai_rmf": (
            "MEASURE 2.7 – security and resilience evaluated and documented",
            "MEASURE 2.10 – privacy risk examined and documented",
        ),
        "eu_ai_act": (
            "Article 10 – data and data governance",
            "Article 15(3) – robustness and cybersecurity",
        ),
        "iso_iec_42001": (
            "A.6.2.4 – AI system verification and validation",
            "A.7 – data for AI systems",
        ),
    },
    "rag_attack": {
        "nist_ai_rmf": ("MEASURE 2.7 – security and resilience evaluated and documented",),
        "eu_ai_act": ("Article 15(3) – robustness and cybersecurity",),
        "iso_iec_42001": (
            "A.6.2.4 – AI system verification and validation",
            "A.7 – data for AI systems",
        ),
    },
    "agent_tool_use": {
        "nist_ai_rmf": ("MEASURE 2.7 – security and resilience evaluated and documented",),
        "eu_ai_act": ("Article 15(3) – robustness and cybersecurity",),
        "iso_iec_42001": ("A.6.2.4 – AI system verification and validation",),
    },
}

SEVERITY_SCORES: Final[dict[FindingSeverity, int]] = {
    FindingSeverity.CRITICAL: 10,
    FindingSeverity.HIGH: 7,
    FindingSeverity.MEDIUM: 5,
    FindingSeverity.LOW: 2,
    FindingSeverity.INFO: 1,
}


class RiskLevel(StrEnum):
    """Aggregated risk level for a report or execution."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


def severity_to_score(severity: FindingSeverity) -> int:
    """Return the numeric risk score for a finding severity."""
    return SEVERITY_SCORES.get(severity, 5)


def compute_risk_score(findings: list[Finding]) -> int:
    """Compute the aggregate risk score for a set of findings.

    The score is the maximum severity score across all findings,
    reflecting the most severe issue found. Returns 0 when there
    are no findings.
    """
    if not findings:
        return 0
    return max(severity_to_score(f.severity) for f in findings)


def compute_risk_level(findings: list[Finding]) -> RiskLevel:
    """Return the aggregated risk level from a set of findings."""
    if not findings:
        return RiskLevel.NONE
    score = compute_risk_score(findings)
    if score >= 10:
        return RiskLevel.CRITICAL
    if score >= 7:
        return RiskLevel.HIGH
    if score >= 5:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def map_category_to_owasp(category: str | None) -> str | None:
    """Map a test case category string to its OWASP LLM Top 10 classification.

    Returns None if the category is unknown.
    """
    if category is None:
        return None
    return OWASP_LLM_TOP_10.get(category)


def map_category_to_compliance(category: str | None) -> dict[str, list[str]]:
    """Return the framework crosswalk for a category.

    The result is a copy so callers cannot mutate the module-level constant.
    Unknown categories return an empty mapping rather than a guessed one.
    """

    if category is None:
        return {}
    crosswalk = COMPLIANCE_CROSSWALK.get(category, {})
    return {framework: list(references) for framework, references in crosswalk.items()}


def extract_test_category(test_config: dict | None) -> str | None:
    """Extract the test case category from a SecurityTest's config dict."""
    config = test_config or {}
    category_str = config.get("category")
    if category_str is None:
        grading = config.get("grading", {})
        if isinstance(grading, dict):
            category_str = grading.get("category")
    return str(category_str) if category_str else None


def execution_result_label(result: ExecutionResult) -> str:
    """Return a human-readable label for an execution result."""
    return {
        ExecutionResult.PASS: "Pass",
        ExecutionResult.FAIL: "Fail",
        ExecutionResult.INCONCLUSIVE: "Inconclusive",
        ExecutionResult.NO_FINDINGS: "Pass (no findings)",
        ExecutionResult.NEEDS_REVIEW: "Needs review (unconfirmed findings)",
    }.get(result, "Inconclusive")


__all__ = [
    "COMPLIANCE_CROSSWALK",
    "OWASP_LLM_TOP_10",
    "OWASP_LLM_TOP_10_VERSION",
    "RiskLevel",
    "SEVERITY_SCORES",
    "compute_risk_level",
    "compute_risk_score",
    "execution_result_label",
    "extract_test_category",
    "map_category_to_compliance",
    "map_category_to_owasp",
    "severity_to_score",
]

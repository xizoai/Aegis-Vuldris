"""Risk scoring tests for Aegis Vuldris."""

from app.models.finding import Finding, FindingSeverity
from app.services.risk_scoring import (
    OWASP_LLM_TOP_10_VERSION,
    RiskLevel,
    compute_risk_level,
    compute_risk_score,
    extract_test_category,
    map_category_to_compliance,
    map_category_to_owasp,
    severity_to_score,
)


def test_severity_to_score_returns_correct_values() -> None:
    assert severity_to_score(FindingSeverity.CRITICAL) == 10
    assert severity_to_score(FindingSeverity.HIGH) == 7
    assert severity_to_score(FindingSeverity.MEDIUM) == 5
    assert severity_to_score(FindingSeverity.LOW) == 2
    assert severity_to_score(FindingSeverity.INFO) == 1


def test_compute_risk_score_returns_max_severity() -> None:
    findings = [
        Finding(title="a", severity=FindingSeverity.LOW),
        Finding(title="b", severity=FindingSeverity.CRITICAL),
        Finding(title="c", severity=FindingSeverity.MEDIUM),
    ]
    assert compute_risk_score(findings) == 10


def test_compute_risk_score_empty_returns_zero() -> None:
    assert compute_risk_score([]) == 0


def test_compute_risk_level_critical() -> None:
    findings = [Finding(title="x", severity=FindingSeverity.CRITICAL)]
    assert compute_risk_level(findings) == RiskLevel.CRITICAL


def test_compute_risk_level_high() -> None:
    findings = [Finding(title="x", severity=FindingSeverity.HIGH)]
    assert compute_risk_level(findings) == RiskLevel.HIGH


def test_compute_risk_level_medium() -> None:
    findings = [Finding(title="x", severity=FindingSeverity.MEDIUM)]
    assert compute_risk_level(findings) == RiskLevel.MEDIUM


def test_compute_risk_level_low() -> None:
    findings = [Finding(title="x", severity=FindingSeverity.LOW)]
    assert compute_risk_level(findings) == RiskLevel.LOW


def test_compute_risk_level_none() -> None:
    assert compute_risk_level([]) == RiskLevel.NONE


def test_map_category_to_owasp_known() -> None:
    assert OWASP_LLM_TOP_10_VERSION == "2026"
    assert map_category_to_owasp("prompt_injection") == "LLM01:2026 – Prompt Injection"
    assert map_category_to_owasp("jailbreak") == "LLM01:2026 – Prompt Injection"
    assert (
        map_category_to_owasp("privacy_data_leakage")
        == "LLM02:2026 – Sensitive Information Disclosure"
    )
    assert map_category_to_owasp("rag_attack") == "LLM09:2026 – Vector and Embedding Weaknesses"
    assert map_category_to_owasp("agent_tool_use") == "LLM03:2026 – Excessive Agency"


def test_map_category_to_compliance_returns_copy_of_crosswalk() -> None:
    crosswalk = map_category_to_compliance("prompt_injection")
    assert crosswalk["nist_ai_rmf"] == [
        "MEASURE 2.7 – security and resilience evaluated and documented"
    ]
    assert any("Article 55(1)(a)" in reference for reference in crosswalk["eu_ai_act"])
    assert crosswalk["iso_iec_42001"] == ["A.6.2.4 – AI system verification and validation"]

    # Callers must not be able to mutate the module-level constant.
    crosswalk["nist_ai_rmf"].append("mutated")
    assert "mutated" not in map_category_to_compliance("prompt_injection")["nist_ai_rmf"]


def test_map_category_to_compliance_unknown_returns_empty() -> None:
    assert map_category_to_compliance("unknown_category") == {}
    assert map_category_to_compliance(None) == {}


def test_map_category_to_owasp_unknown_returns_none() -> None:
    assert map_category_to_owasp("unknown_category") is None
    assert map_category_to_owasp(None) is None


def test_extract_test_category_from_config() -> None:
    config = {"category": "prompt_injection", "grading": {}}
    assert extract_test_category(config) == "prompt_injection"


def test_extract_test_category_from_grading() -> None:
    config = {"grading": {"category": "jailbreak"}}
    assert extract_test_category(config) == "jailbreak"


def test_extract_test_category_missing_returns_none() -> None:
    assert extract_test_category({}) is None
    assert extract_test_category(None) is None

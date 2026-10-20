"""Tests for the test case schema and service."""

from pathlib import Path

import pytest
from app.schemas.test_case import (
    GradingConfig,
    GradingMethod,
    JudgeConfig,
    TestCase,
    TestCaseCategory,
    TestCaseMessage,
    TestCaseTurn,
)
from app.services.test_cases import load_test_case, load_test_cases_from_dir
from pydantic import ValidationError

TEST_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "backend/app/test_cases"


def test_load_single_test_case_valid() -> None:
    """A valid YAML file loads and validates correctly."""
    case = load_test_case(TEST_CASES_DIR / "prompt_injection/01_direct_instruction_override.yaml")
    assert case.name == "Direct instruction override"
    assert case.category == TestCaseCategory.PROMPT_INJECTION
    assert case.provider == "openai_compatible"
    assert case.grading.method == GradingMethod.KEYWORD
    assert "system prompt" in case.grading.patterns
    assert case.grading.severity == "high"
    assert case.attack_id == "builtin/prompt-injection/01-direct-instruction-override"
    assert case.version == "1.0.0"


def test_load_all_test_cases_from_dir() -> None:
    """All seeded test case files load without validation errors."""
    cases = load_test_cases_from_dir(TEST_CASES_DIR)
    assert len(cases) >= 200
    categories = {c.category for c in cases}
    assert categories == {
        TestCaseCategory.PROMPT_INJECTION,
        TestCaseCategory.JAILBREAK,
        TestCaseCategory.PRIVACY_LEAKAGE,
        TestCaseCategory.RAG_ATTACK,
        TestCaseCategory.AGENT_TOOL_USE,
    }


def test_test_case_to_config_single_turn() -> None:
    """to_config produces a dict with the expected keys for single-turn."""
    case = TestCase(
        name="Test",
        category=TestCaseCategory.PROMPT_INJECTION,
        provider="openai_compatible",
        prompts=[TestCaseMessage(role="user", content="Hello")],
        expected_safe_behavior="Refuse to comply.",
        grading=GradingConfig(patterns=["secret"], severity="high"),
    )
    config = case.to_config()
    assert config["prompts"] == [{"role": "user", "content": "Hello"}]
    assert config["grading"]["patterns"] == ["secret"]
    assert config["grading"]["severity"] == "high"
    assert config["max_retries"] == 0
    assert config["timeout_seconds"] == 30.0


def test_loaded_case_persists_reproducibility_metadata() -> None:
    case = load_test_case(TEST_CASES_DIR / "prompt_injection/01_direct_instruction_override.yaml")

    assert case.to_config()["attack"] == {
        "id": "builtin/prompt-injection/01-direct-instruction-override",
        "version": "1.0.0",
        "category": "prompt_injection",
        "security_property": case.expected_safe_behavior,
        "references": [],
        "known_limitations": [],
    }


def test_test_case_to_config_multi_turn() -> None:
    """to_config includes turns for multi-turn test cases."""
    case = TestCase(
        name="Multi",
        category=TestCaseCategory.PROMPT_INJECTION,
        provider="openai_compatible",
        turns=[
            TestCaseTurn(messages=[TestCaseMessage(role="user", content="Q1")]),
            TestCaseTurn(messages=[TestCaseMessage(role="user", content="Q2")]),
        ],
        expected_safe_behavior="Refuse to comply.",
        grading=GradingConfig(patterns=["leak"]),
    )
    config = case.to_config()
    assert "turns" in config
    assert len(config["turns"]) == 2
    assert config["turns"][0]["messages"][0]["content"] == "Q1"
    assert config["turns"][1]["messages"][0]["content"] == "Q2"


def test_test_case_to_config_system_prompt() -> None:
    """to_config includes system_prompt when set."""
    case = TestCase(
        name="Sys",
        category=TestCaseCategory.PROMPT_INJECTION,
        provider="openai_compatible",
        system_prompt="You are a test assistant.",
        prompts=[TestCaseMessage(role="user", content="Hi")],
        expected_safe_behavior="Be safe.",
    )
    config = case.to_config()
    assert config["system_prompt"] == "You are a test assistant."


def test_invalid_category_raises() -> None:
    """An invalid category value raises ValidationError."""
    with pytest.raises(ValidationError):
        TestCase(
            name="Bad",
            category="not_a_real_category",  # type: ignore[arg-type]
            provider="openai_compatible",
            expected_safe_behavior="Be safe.",
        )


def test_missing_required_field_raises() -> None:
    """Missing required fields raise ValidationError."""
    with pytest.raises(ValidationError):
        TestCase(
            name="Missing",
            category=TestCaseCategory.PROMPT_INJECTION,
            provider="openai_compatible",
            expected_safe_behavior="Be safe.",
            grading=GradingConfig(method="invalid_method"),  # type: ignore[arg-type]
        )


def test_judge_config_validation() -> None:
    """JudgeConfig with valid fields validates and serializes."""
    case = TestCase(
        name="Judge",
        category=TestCaseCategory.PROMPT_INJECTION,
        provider="openai_compatible",
        prompts=[TestCaseMessage(role="user", content="Hello")],
        expected_safe_behavior="Be safe.",
        grading=GradingConfig(
            method=GradingMethod.JUDGE_MODEL,
            judge=JudgeConfig(
                model="gpt-4o",
                prompt="Evaluate: {{response}}",
                pass_indicator="safe",
                fail_indicator="unsafe",
            ),
        ),
    )
    config = case.to_config()
    assert config["grading"]["method"] == "judge_model"
    assert config["grading"]["judge"]["model"] == "gpt-4o"
    assert config["grading"]["judge"]["pass_indicator"] == "safe"


def test_extra_fields_rejected() -> None:
    """TestCase with extra fields raises ValidationError (extra='forbid')."""
    with pytest.raises(ValidationError):
        TestCase(
            name="Extra",
            category=TestCaseCategory.PROMPT_INJECTION,
            provider="openai_compatible",
            expected_safe_behavior="Be safe.",
            unexpected_field="should not be here",  # type: ignore[unexpected-type]
        )


def test_load_invalid_yaml_raises(tmp_path: Path) -> None:
    """A structurally invalid YAML raises ValidationError."""
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("name: Bad\ncategory: not_real\nprovider: x\nexpected_safe_behavior: y\n")
    with pytest.raises(ValidationError):
        load_test_case(bad_file)

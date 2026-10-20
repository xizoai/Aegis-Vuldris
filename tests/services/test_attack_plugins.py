"""Tests for the safe, declarative internal attack-plugin registry."""

from pathlib import Path

import pytest
from app.schemas.test_case import TestCase, TestCaseCategory
from app.services.attack_plugins import AttackPlugin, AttackPluginRegistry, load_attack_plugins

TEST_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "backend/app/test_cases"


def _case(*, attack_id: str = "community/example") -> TestCase:
    return TestCase(
        attack_id=attack_id,
        name="Example attack",
        category=TestCaseCategory.PROMPT_INJECTION,
        provider="openai_compatible",
        expected_safe_behavior="Refuse the unsafe request.",
    )


def test_bundled_plugins_have_unique_stable_identities() -> None:
    registry = load_attack_plugins(TEST_CASES_DIR)
    plugins = registry.all()

    assert len(plugins) == 224
    assert len({plugin.key for plugin in plugins}) == len(plugins)
    assert all(plugin.execution_config()["attack"]["id"] == plugin.attack_id for plugin in plugins)


def test_duplicate_plugin_identity_is_rejected() -> None:
    registry = AttackPluginRegistry()
    registry.register(AttackPlugin.from_case(_case()))

    with pytest.raises(ValueError, match="duplicate attack plugin identity"):
        registry.register(AttackPlugin.from_case(_case()))


def test_plugins_can_be_selected_by_capability_category() -> None:
    registry = AttackPluginRegistry()
    registry.register(AttackPlugin.from_case(_case(attack_id="community/prompt")))
    registry.register(
        AttackPlugin.from_case(
            TestCase(
                attack_id="community/rag",
                name="RAG attack",
                category=TestCaseCategory.RAG_ATTACK,
                provider="openai_compatible",
                expected_safe_behavior="Reject unauthorized retrieval.",
            )
        )
    )

    assert [plugin.attack_id for plugin in registry.by_category(TestCaseCategory.RAG_ATTACK)] == [
        "community/rag"
    ]

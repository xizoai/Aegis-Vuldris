"""Model-profile resolution and run-manifest tests."""

from uuid import uuid4

from app.models.target import Target, TargetProvider
from app.models.test import SecurityTest
from app.services.model_profile import (
    build_run_manifest,
    resolved_generation_config,
    resolved_system_prompt,
)


def _target(**overrides) -> Target:
    values = {
        "id": uuid4(),
        "project_id": uuid4(),
        "name": "Candidate model",
        "provider": TargetProvider.OPENAI_COMPATIBLE,
        "endpoint": "https://model.example.com/v1",
        "model": "candidate-v1",
        "model_version": "2026-08-01",
        "system_prompt": "Target system prompt",
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 512,
        "seed": 7,
        "capabilities": ["chat"],
        "timeout_seconds": 30.0,
        "rate_limit_per_minute": 60,
    }
    values.update(overrides)
    return Target(**values)


def _test(config: dict) -> SecurityTest:
    return SecurityTest(
        id=uuid4(),
        project_id=uuid4(),
        name="Prompt injection case",
        provider="openai_compatible",
        config=config,
    )


def test_resolved_generation_prefers_test_values_and_fills_gaps() -> None:
    target = _target()

    resolved = resolved_generation_config(
        {"temperature": 0.7, "max_tokens": 300},
        target,
    )

    assert resolved == {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 300,
        "seed": 7,
    }


def test_resolved_generation_uses_target_defaults_when_test_is_empty() -> None:
    resolved = resolved_generation_config({}, _target())

    assert resolved == {
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 512,
        "seed": 7,
    }


def test_resolved_system_prompt_prefers_test_then_target() -> None:
    prompt, source = resolved_system_prompt(
        {"system_prompt": "Test system prompt"},
        _target(),
    )
    assert (prompt, source) == ("Test system prompt", "test")

    prompt, source = resolved_system_prompt({}, _target())
    assert (prompt, source) == ("Target system prompt", "target")

    prompt, source = resolved_system_prompt({}, _target(system_prompt=None))
    assert (prompt, source) == (None, None)


def test_build_run_manifest_captures_profile_and_hashes_test_config() -> None:
    target = _target()
    test = _test(
        {
            "category": "prompt_injection",
            "system_prompt": "Test system prompt",
            "temperature": 0.7,
            "max_tokens": 300,
            "attack": {"id": "pi-001", "version": "1.2"},
            "grading": {"patterns": ["secret"]},
        }
    )

    manifest = build_run_manifest(target, test)

    assert manifest["manifest_version"] == 1
    assert manifest["target"]["model"] == "candidate-v1"
    assert manifest["target"]["model_version"] == "2026-08-01"
    assert manifest["target"]["generation_defaults"] == {
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 512,
        "seed": 7,
    }
    assert manifest["effective_generation"] == {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 300,
        "seed": 7,
    }
    assert manifest["test"]["category"] == "prompt_injection"
    assert manifest["test"]["attack_id"] == "pi-001"
    assert manifest["test"]["attack_version"] == "1.2"
    assert len(manifest["test"]["config_sha256"]) == 64
    assert manifest["system_prompt_source"] == "test"
    # The manifest proves which prompt was used without copying its text.
    assert "Test system prompt" not in str(manifest)
    assert manifest["target"]["system_prompt_sha256"]
    assert manifest["target"]["system_prompt_length"] == len("Test system prompt")

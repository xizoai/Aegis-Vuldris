"""Model-profile resolution and run-manifest construction.

A model name is not a model version, and a prompt result is not reproducible
without the generation settings that produced it. These helpers resolve the
effective settings for one run (test overrides win over target defaults) and
build the immutable manifest stored on the execution.

The manifest intentionally contains digests rather than copies of prompt
content. The target's system prompt can contain sensitive deployment detail;
the exact text already travels with the execution transcript, while the
manifest only needs to prove *which* text was used.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.models.target import Target
from app.models.test import SecurityTest

MANIFEST_VERSION = 1


def _sha256(value: str) -> str:
    """Return a stable hex digest for a string value."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _config_digest(config: dict[str, Any]) -> str:
    """Return a stable digest of a test's execution configuration."""

    serialized = json.dumps(config, sort_keys=True, default=str, separators=(",", ":"))
    return _sha256(serialized)


def resolved_generation_config(
    test_config: dict[str, Any] | None,
    target: Target,
) -> dict[str, Any]:
    """Resolve effective generation settings for a run.

    A test case's explicit value is the more specific instruction and wins.
    The target's model profile fills every value the test leaves unset.
    ``system_prompt`` is resolved separately by the caller because it is sent
    as a message rather than a generation parameter.
    """

    config = test_config or {}
    temperature = config.get("temperature")
    if temperature is None:
        temperature = target.temperature
    top_p = config.get("top_p")
    if top_p is None:
        top_p = target.top_p
    max_tokens = config.get("max_tokens")
    if max_tokens is None:
        max_tokens = target.max_tokens
    seed = config.get("seed")
    if seed is None:
        seed = target.seed

    return {
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "seed": seed,
    }


def resolved_system_prompt(
    test_config: dict[str, Any] | None,
    target: Target,
) -> tuple[str | None, str | None]:
    """Return ``(system_prompt, source)`` for a run.

    ``source`` is ``"test"`` or ``"target"`` when a prompt is present, and
    ``None`` when neither configures one.
    """

    config = test_config or {}
    test_prompt = config.get("system_prompt")
    if isinstance(test_prompt, str) and test_prompt:
        return test_prompt, "test"
    if isinstance(target.system_prompt, str) and target.system_prompt:
        return target.system_prompt, "target"
    return None, None


def build_run_manifest(
    target: Target,
    test: SecurityTest,
    *,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the immutable snapshot stored on an execution.

    The target row can change after a run; storing this snapshot with the
    execution is what makes a historical result reproducible. It captures the
    model identifier and declared version, the endpoint, effective generation
    settings, and a digest of the test definition.
    """

    config = test.config if isinstance(test.config, dict) else {}
    effective = resolved_generation_config(config, target)
    system_prompt, system_prompt_source = resolved_system_prompt(config, target)
    category = config.get("category")
    attack = config.get("attack")
    attack = attack if isinstance(attack, dict) else {}

    return {
        "manifest_version": MANIFEST_VERSION,
        "captured_at": (captured_at or datetime.now(UTC)).isoformat(),
        "target": {
            "id": str(target.id),
            "name": target.name,
            "provider": target.provider.value,
            "endpoint": target.endpoint,
            "model": target.model,
            "model_version": target.model_version,
            "generation_defaults": {
                "temperature": target.temperature,
                "top_p": target.top_p,
                "max_tokens": target.max_tokens,
                "seed": target.seed,
            },
            "system_prompt_sha256": _sha256(system_prompt) if system_prompt else None,
            "system_prompt_length": len(system_prompt) if system_prompt else 0,
        },
        "test": {
            "id": str(test.id),
            "name": test.name,
            "category": category if isinstance(category, str) else None,
            "attack_id": attack.get("id"),
            "attack_version": attack.get("version"),
            "config_sha256": _config_digest(config),
        },
        "effective_generation": effective,
        "system_prompt_source": system_prompt_source,
    }


__all__ = [
    "MANIFEST_VERSION",
    "build_run_manifest",
    "resolved_generation_config",
    "resolved_system_prompt",
]

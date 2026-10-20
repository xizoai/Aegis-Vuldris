"""``docs/configuration.md`` must not drift from its sources.

The project treats ``.env.example`` as the single source of environment truth.
These tests regenerate the reference through the same code the script uses and
compare it byte-for-byte, so a new setting or a new variable cannot land
undocumented and a removed one cannot linger in the docs.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest
from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "configuration.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
GENERATOR = REPO_ROOT / "scripts" / "generate_configuration_docs.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_configuration_docs", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configuration_doc_is_up_to_date() -> None:
    generator = _load_generator()
    try:
        rendered = generator.render()
    except SystemExit as exc:  # the generator reports coverage problems this way
        pytest.fail(str(exc))
    assert DOC_PATH.read_text(encoding="utf-8") == rendered, (
        "docs/configuration.md is stale; run python scripts/generate_configuration_docs.py"
    )


def test_every_setting_appears_in_env_example() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for name in Settings.model_fields:
        assert re.search(rf"^{name.upper()}=", text, flags=re.MULTILINE), (
            f"Settings field {name} is missing from .env.example"
        )

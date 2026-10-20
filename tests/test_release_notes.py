"""Release-notes extractor tests.

`scripts/extract_release_notes.py` builds the GitHub Release body in CI. Its
two failure modes matter most: a tag without a changelog section must fail
loudly, and the migration head it reports must be a real revision.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "extract_release_notes.py"


def _load_extractor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("extract_release_notes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changelog_section_is_extracted() -> None:
    extractor = _load_extractor()
    # The Unreleased section is empty between releases; extract the current
    # release section to verify that the body is included.
    section = extractor.changelog_section("0.1.0")
    assert section.startswith("## [0.1.0]")
    assert "### Added" in section


def test_missing_changelog_section_fails_loudly() -> None:
    extractor = _load_extractor()
    try:
        extractor.changelog_section("9.9.9")
    except SystemExit as exc:
        assert "no section" in str(exc)
    else:
        raise AssertionError("a missing changelog section must raise SystemExit")


def test_migration_head_is_a_single_real_revision() -> None:
    extractor = _load_extractor()
    head = extractor.migration_head()

    # The repo's revision ids are 12 hex characters.
    assert re.fullmatch(r"[0-9a-f]{12}", head), f"unexpected revision id: {head}"

    # And the head must be defined in the migrations directory.
    found = any(
        f'revision: str = "{head}"' in path.read_text(encoding="utf-8")
        or f'revision = "{head}"' in path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "alembic" / "versions").glob("*.py")
    )
    assert found, f"reported head {head} is not defined by any migration file"


def test_render_appends_upgrade_notes() -> None:
    extractor = _load_extractor()
    body = extractor.render("Unreleased")
    assert "## [Unreleased]" in body
    assert "## Upgrade notes" in body
    assert f"`{extractor.migration_head()}`" in body
    assert "alembic upgrade head" in body

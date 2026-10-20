"""Test case loading and validation for Aegis Vuldris.

Loads security test case definitions from YAML or JSON files, validates
them against the ``TestCase`` schema, and converts them into the config
dict format consumed by ``SecurityTest``.
"""

import json
import re
from pathlib import Path

import yaml

from app.schemas.test_case import TestCase, TestCaseCategory


def load_test_case(path: str | Path) -> TestCase:
    """Load and validate a single test case from a YAML or JSON file.

    The file extension determines the parser: ``.yaml``/``.yml`` uses
    ``yaml.safe_load``; ``.json`` uses ``json.load``.
    """

    file_path = Path(path)
    raw = _read_file(file_path)
    case = TestCase.model_validate(raw)
    if case.attack_id is not None:
        return case
    return case.model_copy(update={"attack_id": _legacy_attack_id(file_path)})


def load_test_cases_from_dir(directory: str | Path) -> list[TestCase]:
    """Load all ``.yaml``/``.yml``/``.json`` test case files in a directory.

    Subdirectories are searched recursively. Files are sorted by name for
    deterministic ordering.
    """

    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"test case directory does not exist: {dir_path}")

    cases: list[TestCase] = []
    for ext in ("*.yaml", "*.yml", "*.json"):
        for file_path in sorted(dir_path.rglob(ext)):
            cases.append(load_test_case(file_path))
    return cases


def load_test_cases_by_category(
    directory: str | Path,
) -> dict[TestCaseCategory, list[TestCase]]:
    """Load test cases from a directory, grouped by category."""

    cases = load_test_cases_from_dir(directory)
    grouped: dict[TestCaseCategory, list[TestCase]] = {}
    for case in cases:
        grouped.setdefault(case.category, []).append(case)
    return grouped


def test_cases_to_configs(cases: list[TestCase]) -> list[dict]:
    """Convert a list of test cases to ``SecurityTest.config`` dicts."""

    return [case.to_config() for case in cases]


def _read_file(file_path: Path) -> dict:
    """Read a YAML or JSON file and return its parsed contents."""

    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif file_path.suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(
            f"unsupported test case file format: {file_path.suffix}. Use .yaml, .yml, or .json."
        )
    if not isinstance(data, dict):
        raise ValueError(f"test case file {file_path} must contain a YAML/JSON object")
    return data


def _legacy_attack_id(file_path: Path) -> str:
    """Create a deterministic ID for a legacy YAML case without one.

    The file path is deliberately used only as a compatibility bridge. New
    contributed attacks should declare ``attack_id`` explicitly so moving a
    file does not change its identity.
    """

    category = re.sub(r"[^a-z0-9]+", "-", file_path.parent.name.lower()).strip("-")
    name = re.sub(r"[^a-z0-9]+", "-", file_path.stem.lower()).strip("-")
    return f"builtin/{category}/{name}"


__all__ = [
    "load_test_case",
    "load_test_cases_by_category",
    "load_test_cases_from_dir",
    "test_cases_to_configs",
]

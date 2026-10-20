"""Validated, declarative attack plugins for the internal attack registry.

An attack plugin is data, not imported third-party Python. This keeps the
extension boundary safe: contributors can add a versioned YAML case without
being able to bypass authorization, the execution engine, or network policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.schemas.test_case import TestCase, TestCaseCategory
from app.services.test_cases import load_test_cases_from_dir


@dataclass(frozen=True)
class AttackPlugin:
    """A validated attack definition that can be run by the shared engine."""

    attack_id: str
    version: str
    category: TestCaseCategory
    case: TestCase

    @classmethod
    def from_case(cls, case: TestCase) -> AttackPlugin:
        if case.attack_id is None:
            raise ValueError("attack plugin must have a stable attack_id")
        return cls(
            attack_id=case.attack_id,
            version=case.version,
            category=case.category,
            case=case,
        )

    @property
    def key(self) -> tuple[str, str]:
        """Stable identity for reproducible benchmark and assessment runs."""

        return (self.attack_id, self.version)

    def execution_config(self) -> dict:
        """Return the validated configuration consumed by the executor."""

        return self.case.to_config()


class AttackPluginRegistry:
    """Internal registry of declarative attack plugins.

    Duplicate IDs and versions are rejected at load time, avoiding a
    non-deterministic "last file wins" implementation.
    """

    def __init__(self) -> None:
        self._plugins: dict[tuple[str, str], AttackPlugin] = {}

    def register(self, plugin: AttackPlugin) -> None:
        if plugin.key in self._plugins:
            raise ValueError(
                f"duplicate attack plugin identity: {plugin.attack_id!r} version {plugin.version!r}"
            )
        self._plugins[plugin.key] = plugin

    def all(self) -> tuple[AttackPlugin, ...]:
        """Return plugins in a stable order for reproducible planning."""

        return tuple(self._plugins[key] for key in sorted(self._plugins))

    def by_category(self, category: TestCaseCategory) -> tuple[AttackPlugin, ...]:
        return tuple(plugin for plugin in self.all() if plugin.category == category)


def load_attack_plugins(directory: str | Path) -> AttackPluginRegistry:
    """Load a directory of YAML/JSON attack definitions into a registry."""

    registry = AttackPluginRegistry()
    for case in load_test_cases_from_dir(directory):
        registry.register(AttackPlugin.from_case(case))
    return registry


__all__ = ["AttackPlugin", "AttackPluginRegistry", "load_attack_plugins"]

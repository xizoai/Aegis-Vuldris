"""Versioned third-party extension discovery for Aegis Vuldris.

Four contracts are extensible through Python entry points, all loaded through
this one module so the rules can never drift per group:

- ``aegis.attack_plugins`` — a directory of validated YAML attack cases
  (``cases_dir``); attacks stay data, never imported code.
- ``aegis.adapters`` — a factory for a :class:`BaseTargetAdapter`
  implementation, registered as an override for one provider value.
- ``aegis.graders`` — a :class:`~app.services.grading.ResponseGrader`
  implementation (instance or zero-argument factory).
- ``aegis.report_exporters`` — an artifact writer for an additional report
  format (``format`` + ``write_artifact``).

Rules enforced for every group:

- the loaded object must expose ``PLUGIN_API_VERSION`` equal to
  :data:`PLUGIN_API_VERSION`, otherwise it is rejected with a clear reason —
  never silently skipped, never guessed compatible;
- discovery honors ``ALLOW_THIRD_PARTY_PLUGINS`` (community default: allowed,
  a self-hosted responsibility; a cloud pilot sets it to false so only
  first-party code runs);
- acceptances and rejections are auditable: pass a session and the loader
  records ``plugin.loaded`` / ``plugin.rejected`` rows (actor-less; plugin
  loading is an operator action, not a user action).

Extension loading is *discovery only*: nothing here executes plugin code
beyond importing the named module attribute, and graders/exporters/adapters
still only ever receive the same inputs the built-ins do.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.audit import record_audit_event

PLUGIN_API_VERSION = 1

GROUP_ATTACK_PLUGINS = "aegis.attack_plugins"
GROUP_ADAPTERS = "aegis.adapters"
GROUP_GRADERS = "aegis.graders"
GROUP_REPORT_EXPORTERS = "aegis.report_exporters"


@dataclass(frozen=True)
class LoadedExtension:
    """One discovered entry point and the object it resolved to."""

    name: str
    value: str
    obj: Any


@dataclass(frozen=True)
class RejectedExtension:
    """One entry point that failed a contract rule, with the reason."""

    name: str
    value: str
    reason: str


@dataclass
class ExtensionReport:
    """Outcome of a discovery pass over one entry-point group."""

    group: str
    accepted: list[LoadedExtension] = field(default_factory=list)
    rejected: list[RejectedExtension] = field(default_factory=list)
    disabled: bool = False


def _audit(
    session: Session | None, actor_id: UUID | None, action: str, name: str, detail: str
) -> None:
    if session is None:
        return
    record_audit_event(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="extension",
        resource_id=name,
        event_metadata={"detail": detail},
    )


def _version_reason(obj: Any) -> str | None:
    """Return a rejection reason when the object's API version is wrong."""

    version = getattr(obj, "PLUGIN_API_VERSION", None)
    if version != PLUGIN_API_VERSION:
        return f"PLUGIN_API_VERSION {version!r} does not match supported {PLUGIN_API_VERSION!r}"
    return None


def discover_extensions(
    group: str,
    *,
    session: Session | None = None,
    actor_id: UUID | None = None,
    allow: bool | None = None,
) -> ExtensionReport:
    """Load every entry point in ``group`` and enforce the shared rules."""

    if allow is None:
        allow = get_settings().allow_third_party_plugins

    report = ExtensionReport(group=group)
    if not allow:
        report.disabled = True
        _audit(
            session,
            actor_id,
            "plugin.rejected",
            group,
            "third-party plugin loading is disabled (ALLOW_THIRD_PARTY_PLUGINS=false)",
        )
        return report

    for point in entry_points(group=group):
        try:
            obj = point.load()
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not crash discovery
            reason = f"failed to import: {type(exc).__name__}: {exc}"
            report.rejected.append(RejectedExtension(point.name, point.value, reason))
            _audit(session, actor_id, "plugin.rejected", point.name, reason)
            continue

        reason = _version_reason(obj)
        if reason is not None:
            report.rejected.append(RejectedExtension(point.name, point.value, reason))
            _audit(session, actor_id, "plugin.rejected", point.name, reason)
            continue

        report.accepted.append(LoadedExtension(point.name, point.value, obj))
        _audit(session, actor_id, "plugin.loaded", point.name, f"{group}: {point.value}")

    return report


def _contract(report: ExtensionReport, predicate: Callable[[Any], str | None]) -> ExtensionReport:
    """Apply a group-specific contract on top of the shared rules.

    Rejections from the shared layer (policy, import failures, version
    mismatches) are carried over: the group contract narrows what is
    *accepted*, it must never hide what was rejected.
    """

    surviving = ExtensionReport(group=report.group, disabled=report.disabled)
    surviving.rejected.extend(report.rejected)
    for extension in report.accepted:
        reason = predicate(extension.obj)
        if reason is None:
            surviving.accepted.append(extension)
        else:
            surviving.rejected.append(RejectedExtension(extension.name, extension.value, reason))
    return surviving


def discover_graders(**kwargs: Any) -> ExtensionReport:
    """Discover ``ResponseGrader`` implementations (instance or factory)."""

    def _is_grader(obj: Any) -> str | None:
        if hasattr(obj, "grade"):
            return None
        if callable(obj):
            return None
        return "expected a ResponseGrader (an object with .grade) or a zero-argument factory"

    report = discover_extensions(GROUP_GRADERS, **kwargs)
    return _contract(report, _is_grader)


def grader_from(extension: LoadedExtension) -> Any:
    """Resolve a discovered grader entry to a usable instance."""

    obj = extension.obj
    if hasattr(obj, "grade"):
        return obj
    return obj()  # zero-argument factory


def discover_report_exporters(**kwargs: Any) -> ExtensionReport:
    """Discover artifact writers for additional report formats."""

    def _is_exporter(obj: Any) -> str | None:
        if not isinstance(getattr(obj, "format", None), str):
            return "expected a string 'format' attribute"
        if not callable(getattr(obj, "write_artifact", None)):
            return "expected a callable write_artifact(data, out_dir) -> Path"
        return None

    report = discover_extensions(GROUP_REPORT_EXPORTERS, **kwargs)
    return _contract(report, _is_exporter)


def discover_attack_plugin_dirs(**kwargs: Any) -> ExtensionReport:
    """Discover directories of YAML attack cases (attacks are data, not code)."""

    def _has_cases_dir(obj: Any) -> str | None:
        cases_dir = getattr(obj, "cases_dir", None)
        if not isinstance(cases_dir, (str, Path)):
            return "expected a 'cases_dir' path attribute pointing at a directory of YAML cases"
        if not Path(cases_dir).is_dir():
            return f"cases_dir {cases_dir!r} is not a directory"
        return None

    report = discover_extensions(GROUP_ATTACK_PLUGINS, **kwargs)
    return _contract(report, _has_cases_dir)


def attack_cases_dirs(report: ExtensionReport) -> list[Path]:
    return [Path(ext.obj.cases_dir) for ext in report.accepted]


def discover_adapter_factories(**kwargs: Any) -> ExtensionReport:
    """Discover ``BaseTargetAdapter`` factories registered per provider value."""

    def _is_adapter_bundle(obj: Any) -> str | None:
        provider = getattr(obj, "provider", None)
        if not isinstance(provider, str):
            return "expected a string 'provider' attribute (an existing provider value)"
        if not callable(getattr(obj, "factory", None)):
            return (
                "expected a callable factory(credential_resolver=...) returning a BaseTargetAdapter"
            )
        return None

    report = discover_extensions(GROUP_ADAPTERS, **kwargs)
    return _contract(report, _is_adapter_bundle)


def summary_line(reports: list[ExtensionReport]) -> str:
    """A one-line, paste-ready summary for ``aegis doctor``."""

    if any(report.disabled for report in reports):
        return (
            "extensions: third-party plugin loading is disabled (ALLOW_THIRD_PARTY_PLUGINS=false)"
        )
    accepted = sum(len(report.accepted) for report in reports)
    rejected = sum(len(report.rejected) for report in reports)
    suffix = f", {rejected} rejected (see audit log)" if rejected else ""
    return f"extensions: {accepted} third-party plugin(s) discovered{suffix}"

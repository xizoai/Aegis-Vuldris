"""Report artifact exporters: the contract behind additional report formats.

A report exporter turns a collected report-data dict into an artifact file.
The two built-in formats (JSON and Markdown) are the reference
implementations; third parties add formats through the
``aegis.report_exporters`` entry-point group (see
``docs/extension-points.md``) without touching
``services/report_generation.py``.

Contract for a third-party exporter:

- expose ``PLUGIN_API_VERSION`` matching
  :data:`app.services.extensions.PLUGIN_API_VERSION`;
- expose a string ``format`` — the value users put in ``ReportCreate.format``
  and the file suffix Aegis Vuldris stores;
- expose ``write_artifact(data: dict, out_dir: Path) -> Path`` — write the
  artifact into ``out_dir`` and return its path. The machine-readable
  ``.data.json`` snapshot is always written by the generator before any
  exporter runs, so exporters only shape the human-facing artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from app.services.extensions import (
    GROUP_REPORT_EXPORTERS,
    LoadedExtension,
    discover_report_exporters,
)


class ReportExporter(Protocol):
    """The contract an artifact writer implements."""

    format: str

    def write_artifact(self, data: dict[str, Any], out_dir: Path) -> Path:
        """Write the artifact for ``data`` into ``out_dir`` and return its path."""
        ...


class JsonReportExporter:
    """Reference implementation: the JSON artifact (the report data as-is)."""

    PLUGIN_API_VERSION = 1
    format = "json"

    def write_artifact(self, data: dict[str, Any], out_dir: Path) -> Path:
        base = _artifact_base(data)
        path = out_dir / f"{base}.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=str)
        return path


class MarkdownReportExporter:
    """Reference implementation: the Markdown artifact.

    Delegates to the generator's writer so the built-in Markdown layout stays
    in exactly one place — third-party exporters show how to wrap it, not how
    to fork it.
    """

    PLUGIN_API_VERSION = 1
    format = "markdown"

    def write_artifact(self, data: dict[str, Any], out_dir: Path) -> Path:
        from app.services.report_generation import _write_markdown_report

        base = _artifact_base(data)
        path = out_dir / f"{base}.md"
        _write_markdown_report(path, data)
        return path


def _artifact_base(data: dict[str, Any]) -> str:
    """Build the deterministic file stem the generator uses for artifacts."""

    return f"report_{data['report_id']}_v{data['report_version']}"


def find_third_party_exporter(
    fmt: str,
    *,
    discovered: list[LoadedExtension] | None = None,
) -> Any | None:
    """Return the exporter registered for ``fmt``, if any.

    ``discovered`` lets a caller that already ran discovery (for example to
    audit or display plugins) pass the result through instead of rescanning.
    """

    extensions = discovered
    if extensions is None:
        extensions = discover_report_exporters().accepted
    for extension in extensions:
        if getattr(extension.obj, "format", None) == fmt:
            return extension.obj
    return None


__all__ = [
    "GROUP_REPORT_EXPORTERS",
    "JsonReportExporter",
    "MarkdownReportExporter",
    "ReportExporter",
    "find_third_party_exporter",
]

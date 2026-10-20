"""Extension contract tests: real entry-point discovery, versioning, policy.

The fixture plugin in ``tests/fixtures/plugins/`` is installed into a
temporary directory together with a hand-crafted ``.dist-info``, so
``importlib.metadata`` discovers it through the same machinery a real
``pip install`` would use — no fake registries, no monkeypatched loaders.
"""

from __future__ import annotations

import shutil
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.adapters.registry import AdapterRegistry
from app.core.config import get_settings
from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.target import TargetProvider
from app.services.attack_plugins import load_attack_plugins
from app.services.extensions import (
    GROUP_ADAPTERS,
    GROUP_ATTACK_PLUGINS,
    GROUP_GRADERS,
    GROUP_REPORT_EXPORTERS,
    PLUGIN_API_VERSION,
    attack_cases_dirs,
    discover_adapter_factories,
    discover_attack_plugin_dirs,
    discover_graders,
    discover_report_exporters,
    grader_from,
    summary_line,
)
from sqlalchemy import select

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plugins"
PLUGIN_MODULE = "fixture_plugin"


@pytest.fixture
def plugin_env(tmp_path: Path) -> Iterator[Path]:
    """Install the fixture plugin package into tmp_path and put it on sys.path."""

    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    dist_info = tmp_path / "aegis_fixture_plugin-0.0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: aegis-fixture-plugin\nVersion: 0.0.1\n",
        encoding="utf-8",
    )
    (dist_info / "entry_points.txt").write_text(
        "\n".join(
            [
                f"[{GROUP_GRADERS}]",
                f"fixture-always-pass = {PLUGIN_MODULE}:FIXTURE_GRADER",
                "",
                f"[{GROUP_REPORT_EXPORTERS}]",
                f"fixture-txt = {PLUGIN_MODULE}:FIXTURE_EXPORTER",
                "",
                f"[{GROUP_ATTACK_PLUGINS}]",
                f"fixture-cases = {PLUGIN_MODULE}:FIXTURE_ATTACKS",
                "",
                f"[{GROUP_ADAPTERS}]",
                f"fixture-openai = {PLUGIN_MODULE}:FIXTURE_ADAPTER_BUNDLE",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # A fresh module per test: the same file is imported from a different
    # directory every time.
    sys.modules.pop(PLUGIN_MODULE, None)
    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    sys.modules.pop(PLUGIN_MODULE, None)


def test_fixture_plugin_is_discovered_in_every_group(plugin_env: Path) -> None:
    graders = discover_graders()
    exporters = discover_report_exporters()
    attacks = discover_attack_plugin_dirs()
    adapters = discover_adapter_factories()

    assert [ext.name for ext in graders.accepted] == ["fixture-always-pass"]
    assert [ext.name for ext in exporters.accepted] == ["fixture-txt"]
    assert [ext.name for ext in attacks.accepted] == ["fixture-cases"]
    assert [ext.name for ext in adapters.accepted] == ["fixture-openai"]
    assert graders.rejected == exporters.rejected == []


def test_discovered_grader_is_usable_by_the_engine(plugin_env: Path) -> None:
    from app.services.execution_engine import ExecutionEngine

    report = discover_graders()
    grader = grader_from(report.accepted[0])

    decision = grader.grade("anything at all", None)
    assert decision.result.value == "pass"
    assert decision.findings == ()
    assert decision.grader_id == "fixture/always-pass"

    # The engine's constructor accepts the discovered grader through the same
    # seam the built-in deterministic grader uses.
    engine = ExecutionEngine(grader=grader)
    assert engine._grader is grader  # noqa: SLF001 - the injection seam under test


def test_discovered_exporter_extends_report_formats(plugin_env: Path) -> None:
    from app.schemas import ProjectCreate, ReportCreate, UserCreate
    from app.services.assessments import create_report
    from app.services.auth import register_user
    from app.services.projects import create_project
    from app.services.report_generation import generate_report

    session = create_session_factory()()
    try:
        owner = register_user(
            session, UserCreate(email=f"ext-{uuid.uuid4()}@example.com", password="x" * 16)
        )
        project = create_project(
            session, ProjectCreate(name=f"Exporter {uuid.uuid4()}"), owner_id=owner.id
        )
        report = create_report(
            session, project.id, ReportCreate(title="txt report", format="txt"), owner
        )

        artifact = Path(generate_report(session, report, plugin_env))

        assert artifact.suffix == ".txt"
        assert "Aegis Vuldris fixture report" in artifact.read_text(encoding="utf-8")
    finally:
        session.close()


def test_attack_extensions_stay_data(plugin_env: Path) -> None:
    report = discover_attack_plugin_dirs()
    dirs = attack_cases_dirs(report)

    registry = load_attack_plugins(dirs[0])
    plugins = registry.all()
    assert len(plugins) >= 1
    assert all(plugin.case.attack_id for plugin in plugins)


def test_discovered_adapter_overrides_the_registry(plugin_env: Path) -> None:
    report = discover_adapter_factories()
    bundle = report.accepted[0].obj

    registry = AdapterRegistry()
    registry.register_override(bundle.provider, bundle.factory)
    adapter = registry.create(TargetProvider.OPENAI_COMPATIBLE)

    assert type(adapter).__name__ == "FixtureAdapter"


def test_unsupported_report_format_is_rejected_loudly(plugin_env: Path) -> None:
    from app.schemas import ProjectCreate, ReportCreate, UserCreate
    from app.services.assessments import create_report
    from app.services.auth import register_user
    from app.services.projects import create_project
    from app.services.report_generation import generate_report

    session = create_session_factory()()
    try:
        owner = register_user(
            session, UserCreate(email=f"ext-{uuid.uuid4()}@example.com", password="x" * 16)
        )
        project = create_project(
            session, ProjectCreate(name=f"No format {uuid.uuid4()}"), owner_id=owner.id
        )
        report = create_report(
            session, project.id, ReportCreate(title="bogus", format="bogus"), owner
        )

        with pytest.raises(ValueError, match="unsupported report format"):
            generate_report(session, report, plugin_env)
    finally:
        session.close()


def test_version_mismatch_is_rejected_and_audited(plugin_env: Path) -> None:
    dist_info = plugin_env / "aegis_fixture_plugin_old-0.0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: aegis-fixture-plugin-old\nVersion: 0.0.1\n",
        encoding="utf-8",
    )
    # A second entry point in the same group pointing at the outdated module.
    # The file is rewritten wholesale: appending at the end would land in the
    # last INI section (aegis.adapters), not in the graders group.
    existing = plugin_env / "aegis_fixture_plugin-0.0.1.dist-info" / "entry_points.txt"
    existing.write_text(
        "\n".join(
            [
                f"[{GROUP_GRADERS}]",
                "fixture-always-pass = fixture_plugin:FIXTURE_GRADER",
                "fixture-old = fixture_plugin_old:OldGrader",
                "",
                f"[{GROUP_REPORT_EXPORTERS}]",
                "fixture-txt = fixture_plugin:FIXTURE_EXPORTER",
                "",
                f"[{GROUP_ATTACK_PLUGINS}]",
                "fixture-cases = fixture_plugin:FIXTURE_ATTACKS",
                "",
                f"[{GROUP_ADAPTERS}]",
                "fixture-openai = fixture_plugin:FIXTURE_ADAPTER_BUNDLE",
                "",
            ]
        ),
        encoding="utf-8",
    )
    sys.modules.pop("fixture_plugin_old", None)

    session = create_session_factory()()
    try:
        report = discover_graders(session=session)

        rejected = {ext.name: ext.reason for ext in report.rejected}
        assert "fixture-old" in rejected
        assert "PLUGIN_API_VERSION" in rejected["fixture-old"]
        assert report.accepted, "the compatible plugin must still load"

        rows = session.scalars(select(AuditLog).where(AuditLog.action == "plugin.rejected")).all()
        assert any("fixture-old" in (row.resource_id or "") for row in rows)
    finally:
        session.close()
        sys.modules.pop("fixture_plugin_old", None)


def test_broken_entry_point_is_rejected_not_fatal(plugin_env: Path) -> None:
    existing = plugin_env / "aegis_fixture_plugin-0.0.1.dist-info" / "entry_points.txt"
    existing.write_text(
        f"[{GROUP_GRADERS}]\n"
        "broken = fixture_plugin:NO_SUCH_ATTRIBUTE\n"
        "alsobroken = no_such_module_at_all:Thing\n",
        encoding="utf-8",
    )

    report = discover_graders()
    assert len(report.rejected) == 2
    assert all("failed to import" in ext.reason for ext in report.rejected)


def test_policy_switch_disables_third_party_loading(plugin_env: Path) -> None:
    settings = get_settings()
    original = settings.allow_third_party_plugins
    settings.allow_third_party_plugins = False
    try:
        report = discover_graders()
        assert report.disabled is True
        assert report.accepted == []
    finally:
        settings.allow_third_party_plugins = original

    explicit = discover_graders(allow=False)
    assert explicit.disabled is True
    assert summary_line([explicit]).startswith("extensions: third-party plugin loading")


def test_summary_line_counts_discovered_plugins(plugin_env: Path) -> None:
    reports = [
        discover_graders(),
        discover_report_exporters(),
        discover_attack_plugin_dirs(),
        discover_adapter_factories(),
    ]
    line = summary_line(reports)
    assert "4 third-party plugin(s) discovered" in line
    assert "rejected" not in line


def test_plugin_api_version_is_exported_and_stable() -> None:
    # The contract version itself: bumping it is a breaking change that must
    # be announced in the changelog and docs together.
    assert PLUGIN_API_VERSION == 1

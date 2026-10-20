"""Ingestion tests: external verdicts to Aegis findings.

The mapping is pure and is covered directly; the persistence path is covered
against the live database so the origin constraint and the replace-on-reingest
behaviour are real rather than assumed.
"""

from uuid import uuid4

from app.db.session import create_session_factory
from app.models.external_scan import ExternalScan, ExternalScanTool
from app.models.finding import Finding, FindingSeverity
from app.models.target import TargetProvider
from app.models.user import User
from app.schemas import ProjectCreate, ScanCreate, TargetCreate, UserCreate
from app.schemas.scan import ScanResultRecord
from app.services.auth import register_user
from app.services.projects import create_project
from app.services.risk_scoring import map_category_to_owasp
from app.services.scan_ingestion import (
    build_scan_finding,
    category_for_probe,
    ingest_scan_results,
    probe_family,
)
from app.services.scans import create_scan
from app.services.targets import create_target
from sqlalchemy import select


def _session():
    return create_session_factory()()


def _record(**overrides) -> ScanResultRecord:
    payload = {
        "probe": "dan.Dan_11_0",
        "detector": "dan.DAN",
        "verdict": "fail",
        "trigger_count": 1,
    }
    payload.update(overrides)
    return ScanResultRecord(**payload)


class _World:
    """A persisted project, target, and scan, cleaned up on dispose."""

    def __init__(self, session) -> None:
        self.session = session
        self.owner: User = register_user(
            session,
            UserCreate(
                email=f"ingest-{uuid4()}@example.com",
                password="a-very-strong-password-123",
            ),
        )
        self.project = create_project(
            session,
            ProjectCreate(name=f"Ingest Project {uuid4()}"),
            owner_id=self.owner.id,
        )
        self.target = create_target(
            session,
            TargetCreate(
                project_id=self.project.id,
                name=f"Ingest Target {uuid4()}",
                provider=TargetProvider.OPENAI_COMPATIBLE,
                endpoint="https://model.example.com/v1",
                model="ingest-model",
                capabilities=["chat"],
                authorization_attestation=True,
            ),
            self.project.id,
            self.owner,
        )
        self.scan = create_scan(
            session,
            self.project.id,
            ScanCreate(
                target_id=self.target.id,
                tool=ExternalScanTool.GARAK,
                config={},
            ),
            self.owner,
        )

    def dispose(self) -> None:
        self.session.delete(self.project)
        self.session.commit()
        self.session.close()


# --- family and category mapping -------------------------------------------


def test_probe_family_is_the_part_before_the_first_dot() -> None:
    assert probe_family("dan.Dan_11_0") == "dan"
    assert probe_family("promptinject.HijackHateHumans") == "promptinject"
    assert probe_family("ENCODING") == "encoding"
    assert probe_family("standalone") == "standalone"


def test_category_falls_back_to_the_probe_family() -> None:
    assert category_for_probe("dan.Dan_11_0") == "jailbreak"
    assert category_for_probe("leakreplay.GuardianCloze") == "privacy_data_leakage"
    # A family with no OWASP entry maps to nothing rather than to a wrong one.
    assert category_for_probe("realtoxicityprompts.RTPBlank") is None
    assert category_for_probe("nope.Nope") is None


def test_reported_category_wins_over_the_family_table() -> None:
    assert category_for_probe("realtoxicityprompts.RTPBlank", "privacy_data_leakage") == (
        "privacy_data_leakage"
    )
    assert category_for_probe("dan.Dan_11_0", "Nothing_Special") == "nothing_special"


# --- finding construction ---------------------------------------------------


def test_failing_verdict_becomes_a_finding_with_owasp_and_tool_details() -> None:
    session = _session()
    world = _World(session)
    try:
        world.scan.tool_version = "0.17.1"
        world.scan.report_path = "/reports/scan-1.report.jsonl"

        finding = build_scan_finding(
            world.scan,
            _record(
                probe="dan.Dan_11_0",
                detector="dan.DAN",
                verdict="fail",
                trigger_count=3,
                record_index=7,
            ),
        )

        assert finding.external_scan_id == world.scan.id
        assert finding.execution_id is None
        assert "Dan_11_0" in finding.title
        assert len(finding.title) <= 200
        assert "jailbreak" in (finding.description or "")
        # Severity comes from the shared scorer, driven by the category text.
        assert finding.severity is FindingSeverity.HIGH

        details = finding.details
        assert details["source"] == "external_scan"
        assert details["tool"] == "garak"
        assert details["tool_version"] == "0.17.1"
        assert details["probe"] == "dan.Dan_11_0"
        assert details["detector"] == "dan.DAN"
        assert details["category"] == "jailbreak"
        assert details["owasp"] == map_category_to_owasp("jailbreak")
        assert details["trigger_count"] == 3
        assert details["record_index"] == 7
        assert details["report_path"] == "/reports/scan-1.report.jsonl"
    finally:
        world.dispose()


def test_finding_never_carries_prompt_or_output_content() -> None:
    """A record has no field for content; the details say so by omission."""

    session = _session()
    world = _World(session)
    try:
        finding = build_scan_finding(world.scan, _record(trigger_count=5))

        assert "trigger" not in finding.details
        assert "prompt" not in finding.details
        assert "outputs" not in finding.details
        assert finding.details["trigger_count"] == 5
    finally:
        world.dispose()


def test_data_leakage_category_escalates_severity() -> None:
    session = _session()
    world = _World(session)
    try:
        finding = build_scan_finding(
            world.scan,
            _record(probe="leakreplay.GuardianCloze", detector="leakreplay.StartsWith"),
        )

        assert finding.details["category"] == "privacy_data_leakage"
        assert finding.severity is FindingSeverity.CRITICAL
    finally:
        world.dispose()


def test_unknown_category_falls_back_to_the_scorer_default() -> None:
    session = _session()
    world = _World(session)
    try:
        finding = build_scan_finding(
            world.scan,
            _record(probe="unknownfamily.SomeProbe", detector=None),
        )

        assert "category" not in finding.details
        assert "owasp" not in finding.details
        assert finding.severity is FindingSeverity.MEDIUM
        # No detector reported: the text must not claim one.
        assert "unnamed detector" in (finding.description or "")
    finally:
        world.dispose()


# --- persistence ------------------------------------------------------------


def test_ingest_persists_only_failures_and_counts_the_rest() -> None:
    session = _session()
    world = _World(session)
    try:
        summary = ingest_scan_results(
            session,
            world.scan,
            [
                _record(probe="dan.Dan_11_0"),
                _record(probe="promptinject.HijackHateHumans", verdict="pass"),
                _record(probe="encoding.InjectBase64", verdict="inconclusive"),
            ],
        )
        session.commit()

        assert summary.findings == 1
        assert summary.passes == 1
        assert summary.inconclusive == 1

        stored = list(
            session.scalars(select(Finding).where(Finding.external_scan_id == world.scan.id)).all()
        )
        assert len(stored) == 1
        assert stored[0].details["probe"] == "dan.Dan_11_0"
    finally:
        world.dispose()


def test_reingesting_a_scan_replaces_its_findings() -> None:
    session = _session()
    world = _World(session)
    try:
        ingest_scan_results(session, world.scan, [_record(probe="dan.Dan_11_0")])
        session.commit()

        ingest_scan_results(
            session,
            world.scan,
            [
                _record(probe="promptinject.HijackHateHumans", detector="promptinject"),
                _record(probe="xss.MarkdownImage", detector="xss"),
            ],
        )
        session.commit()

        stored = list(
            session.scalars(select(Finding).where(Finding.external_scan_id == world.scan.id)).all()
        )
        assert sorted(finding.details["probe"] for finding in stored) == [
            "promptinject.HijackHateHumans",
            "xss.MarkdownImage",
        ]
    finally:
        world.dispose()


def test_ingesting_no_results_clears_a_previous_ingest() -> None:
    session = _session()
    world = _World(session)
    try:
        ingest_scan_results(session, world.scan, [_record()])
        session.commit()

        summary = ingest_scan_results(session, world.scan, [])
        session.commit()

        assert summary.findings == 0
        assert (
            session.scalar(select(Finding).where(Finding.external_scan_id == world.scan.id)) is None
        )
    finally:
        world.dispose()


def test_deleting_a_scan_discards_its_findings() -> None:
    session = _session()
    world = _World(session)
    try:
        ingest_scan_results(session, world.scan, [_record()])
        session.commit()
        scan_id = world.scan.id

        session.delete(session.get(ExternalScan, scan_id))
        session.commit()

        assert session.scalar(select(Finding).where(Finding.external_scan_id == scan_id)) is None
    finally:
        world.dispose()

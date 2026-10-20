"""Report generation and comparison tests for Aegis Vuldris."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.session import create_session_factory
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.finding import Finding, FindingSeverity
from app.models.report import Report
from app.models.test import SecurityTest
from app.models.user import User
from app.schemas import (
    ExecutionCreate,
    FindingCreate,
    ProjectCreate,
    ReportCreate,
    SecurityTestCreate,
    UserCreate,
)
from app.services.assessments import (
    create_execution,
    create_finding,
    create_report,
    create_security_test,
)
from app.services.auth import register_user
from app.services.projects import create_project
from app.services.report_generation import (
    compare_reports,
    generate_report,
    get_report_download_path,
    load_report_snapshot,
)
from sqlalchemy.orm import Session


def _session() -> Session:
    return create_session_factory()()


def _register_user(session: Session) -> User:
    return register_user(
        session,
        UserCreate(
            email=f"report-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )


def _create_project(session: Session, owner: User):
    return create_project(
        session,
        ProjectCreate(name=f"Report Project {uuid4()}"),
        owner_id=owner.id,
    )


def _create_test(session: Session, project_id, owner: User, category: str) -> SecurityTest:
    return create_security_test(
        session,
        project_id,
        SecurityTestCreate(
            name=f"Test {category}",
            provider="openai_compatible",
            config={"category": category, "grading": {"patterns": ["x"]}},
        ),
        owner,
    )


def _create_finding(
    session: Session,
    execution_id,
    title: str,
    severity: FindingSeverity,
    owner: User,
) -> Finding:
    return create_finding(
        session,
        FindingCreate(
            execution_id=execution_id,
            title=title,
            description=f"{title} description",
            severity=severity,
        ),
        owner,
    )


def _seed_execution(session: Session, project_id, owner: User, category: str) -> Execution:
    test = _create_test(session, project_id, owner, category)
    execution = create_execution(
        session,
        project_id,
        ExecutionCreate(test_id=test.id),
        owner,
    )
    execution.status = ExecutionStatus.SUCCEEDED
    execution.result = ExecutionResult.FAIL
    session.commit()
    session.refresh(execution)
    return execution


def test_generate_json_report_populates_path_and_version(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        execution = _seed_execution(session, project.id, owner, "prompt_injection")
        _create_finding(session, execution.id, "Instruction leak", FindingSeverity.HIGH, owner)

        report = create_report(
            session, project.id, ReportCreate(title="Run 1", format="json"), owner
        )
        assert report.path == ""

        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(session, report, Path(tmp))

            assert Path(path).exists()
            assert report.version == 1
            assert report.generated_at is not None
            assert report.path == path

            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert data["risk_score"] == 7
            assert data["risk_level"] == "high"
            assert data["total_findings"] == 1
            assert data["findings_by_severity"]["high"] == 1
            assert data["findings"][0]["owasp_category"].startswith("LLM01")
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_generate_markdown_report_includes_compliance_mapping(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        execution = _seed_execution(session, project.id, owner, "privacy_data_leakage")
        _create_finding(session, execution.id, "PII exposure", FindingSeverity.CRITICAL, owner)

        report = create_report(
            session, project.id, ReportCreate(title="Run MD", format="markdown"), owner
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(session, report, Path(tmp))
            content = Path(path).read_text(encoding="utf-8")

            assert path.endswith(".md")
            assert "# Security Assessment Report" in content
            assert "**Risk Level:** critical" in content
            assert "LLM02:2026" in content
            assert "PII exposure" in content

            # A markdown report still gets a machine-readable snapshot so it
            # remains comparable with other runs.
            assert report.data_path is not None
            assert report.data_path.endswith(".data.json")
            snapshot = load_report_snapshot(session, report.id, project.id)
            assert snapshot["risk_level"] == "critical"
            assert [f["title"] for f in snapshot["findings"]] == ["PII exposure"]
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_regenerating_report_increments_version(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        report = create_report(session, project.id, ReportCreate(title="Versioned"), owner)

        with tempfile.TemporaryDirectory() as tmp:
            generate_report(session, report, Path(tmp))
            first_path = report.path
            assert report.version == 1

            generate_report(session, report, Path(tmp))
            second_path = report.path
            assert report.version == 2

            assert first_path != second_path
            assert Path(first_path).exists()
            assert Path(second_path).exists()
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_report_version_increments_per_report_record(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        first = create_report(session, project.id, ReportCreate(title="A"), owner)
        second = create_report(session, project.id, ReportCreate(title="B"), owner)

        # A report that has never been generated carries version 0.
        assert first.version == 0
        assert second.version == 0

        with tempfile.TemporaryDirectory() as tmp:
            generate_report(session, first, Path(tmp))
            assert first.version == 1

            generate_report(session, second, Path(tmp))
            assert second.version == 1
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_get_report_download_path_returns_generated_file(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        report = create_report(session, project.id, ReportCreate(title="Download"), owner)

        with pytest.raises(FileNotFoundError):
            get_report_download_path(session, report.id, project.id)

        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(session, report, Path(tmp))
            resolved = get_report_download_path(session, report.id, project.id)
            assert str(resolved) == path
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_get_report_download_path_rejects_other_project(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)
    other = _create_project(session, owner)

    try:
        report = create_report(session, project.id, ReportCreate(title="Scoped"), owner)

        with tempfile.TemporaryDirectory() as tmp:
            generate_report(session, report, Path(tmp))
            with pytest.raises(FileNotFoundError):
                get_report_download_path(session, report.id, other.id)
    finally:
        session.delete(other)
        session.delete(project)
        session.commit()
        session.close()


def test_report_with_no_findings_scores_zero(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        report = create_report(session, project.id, ReportCreate(title="Clean"), owner)

        with tempfile.TemporaryDirectory() as tmp:
            path = generate_report(session, report, Path(tmp))
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert data["risk_score"] == 0
            assert data["risk_level"] == "none"
            assert data["total_findings"] == 0
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_compare_reports_detects_new_and_resolved(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            # Baseline run: one finding.
            baseline_execution = _seed_execution(session, project.id, owner, "prompt_injection")
            _create_finding(
                session, baseline_execution.id, "Baseline issue", FindingSeverity.HIGH, owner
            )
            baseline = create_report(session, project.id, ReportCreate(title="Baseline"), owner)
            generate_report(session, baseline, out)

            # Later run: baseline finding is gone, a new one appears.
            session.delete(baseline_execution)
            session.commit()

            current_execution = _seed_execution(session, project.id, owner, "prompt_injection")
            _create_finding(
                session, current_execution.id, "New issue", FindingSeverity.CRITICAL, owner
            )
            current = create_report(session, project.id, ReportCreate(title="Current"), owner)
            generate_report(session, current, out)

            diff = compare_reports(session, baseline.id, current.id, project.id)

            assert diff["resolved_count"] == 1
            assert diff["resolved_findings"][0]["title"] == "Baseline issue"
            assert diff["new_count"] == 1
            assert diff["new_findings"][0]["title"] == "New issue"
            assert diff["regressed_count"] == 0
            assert diff["improved_count"] == 0
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_compare_reports_detects_severity_regression(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            first_execution = _seed_execution(session, project.id, owner, "rag_attack")
            _create_finding(
                session, first_execution.id, "Poisoned document", FindingSeverity.LOW, owner
            )
            first = create_report(session, project.id, ReportCreate(title="First"), owner)
            generate_report(session, first, out)

            session.delete(first_execution)
            session.commit()

            second_execution = _seed_execution(session, project.id, owner, "rag_attack")
            _create_finding(
                session, second_execution.id, "Poisoned document", FindingSeverity.HIGH, owner
            )
            second = create_report(session, project.id, ReportCreate(title="Second"), owner)
            generate_report(session, second, out)

            diff = compare_reports(session, first.id, second.id, project.id)

            assert diff["regressed_count"] == 1
            assert diff["improved_count"] == 0
            assert diff["new_count"] == 0
            assert diff["resolved_count"] == 0
            entry = diff["regressed_findings"][0]
            assert entry["severity_before"] == "low"
            assert entry["severity_after"] == "high"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_compare_reports_detects_severity_improvement(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            first_execution = _seed_execution(session, project.id, owner, "rag_attack")
            _create_finding(
                session, first_execution.id, "Poisoned document", FindingSeverity.CRITICAL, owner
            )
            first = create_report(session, project.id, ReportCreate(title="First"), owner)
            generate_report(session, first, out)

            session.delete(first_execution)
            session.commit()

            second_execution = _seed_execution(session, project.id, owner, "rag_attack")
            _create_finding(
                session, second_execution.id, "Poisoned document", FindingSeverity.LOW, owner
            )
            second = create_report(session, project.id, ReportCreate(title="Second"), owner)
            generate_report(session, second, out)

            diff = compare_reports(session, first.id, second.id, project.id)

            assert diff["improved_count"] == 1
            assert diff["regressed_count"] == 0
            entry = diff["improved_findings"][0]
            assert entry["severity_before"] == "critical"
            assert entry["severity_after"] == "low"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_generate_report_with_baseline_embeds_changes_section(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        # Baseline: a report generated while the project had one finding.
        baseline_execution = _seed_execution(session, project.id, owner, "prompt_injection")
        _create_finding(
            session, baseline_execution.id, "Baseline issue", FindingSeverity.HIGH, owner
        )
        baseline = create_report(session, project.id, ReportCreate(title="Baseline"), owner)
        generate_report(session, baseline, tmp_path)

        # Later: the old finding is gone and a worse one appears.
        session.delete(baseline_execution)
        session.commit()
        current_execution = _seed_execution(session, project.id, owner, "prompt_injection")
        _create_finding(
            session, current_execution.id, "Fresh issue", FindingSeverity.CRITICAL, owner
        )
        current = create_report(
            session, project.id, ReportCreate(title="Current", format="markdown"), owner
        )

        artifact = generate_report(session, current, tmp_path, baseline_report_id=baseline.id)

        text = Path(artifact).read_text(encoding="utf-8")
        assert "## Changes Since Baseline" in text
        assert f"Baseline report: `{baseline.id}`" in text
        assert "**New:** 1" in text
        assert "**Resolved:** 1" in text
        assert "**Regressed:** 0" in text
        assert "- [critical] Fresh issue" in text

        # The same section is embedded in the machine-readable snapshot.
        data = load_report_snapshot(session, current.id, project.id)
        changes = data["changes_since_baseline"]
        assert changes["baseline_report_id"] == str(baseline.id)
        assert changes["new_findings"][0]["title"] == "Fresh issue"
        assert changes["resolved_findings"][0]["title"] == "Baseline issue"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_generate_report_without_baseline_has_no_changes_section(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        execution = _seed_execution(session, project.id, owner, "prompt_injection")
        _create_finding(session, execution.id, "Lone issue", FindingSeverity.HIGH, owner)
        report = create_report(session, project.id, ReportCreate(title="Plain"), owner)
        generate_report(session, report, tmp_path)

        data = load_report_snapshot(session, report.id, project.id)
        assert "changes_since_baseline" not in data
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_compare_reports_requires_generated_reports(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        first = create_report(session, project.id, ReportCreate(title="First"), owner)
        second = create_report(session, project.id, ReportCreate(title="Second"), owner)

        with pytest.raises(FileNotFoundError):
            compare_reports(session, first.id, second.id, project.id)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_comparison_reads_snapshots_not_live_state(tmp_path: Path) -> None:
    """A report's recorded findings must not change when the DB changes later."""

    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            execution = _seed_execution(session, project.id, owner, "jailbreak")
            _create_finding(session, execution.id, "Original issue", FindingSeverity.HIGH, owner)
            report = create_report(session, project.id, ReportCreate(title="Snapshot"), owner)
            generate_report(session, report, Path(tmp))

            snapshot = load_report_snapshot(session, report.id, project.id)
            assert [f["title"] for f in snapshot["findings"]] == ["Original issue"]

            # Mutate the live database; the snapshot must remain unchanged.
            session.delete(execution)
            session.commit()

            still = load_report_snapshot(session, report.id, project.id)
            assert [f["title"] for f in still["findings"]] == ["Original issue"]
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_compare_reports_rejects_foreign_report(tmp_path: Path) -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)
    other = _create_project(session, owner)

    try:
        report = create_report(session, project.id, ReportCreate(title="Mine"), owner)
        foreign = create_report(session, other.id, ReportCreate(title="Theirs"), owner)

        with tempfile.TemporaryDirectory() as tmp:
            generate_report(session, report, Path(tmp))
            generate_report(session, foreign, Path(tmp))

            with pytest.raises(FileNotFoundError):
                compare_reports(session, report.id, foreign.id, project.id)
    finally:
        session.delete(other)
        session.delete(project)
        session.commit()
        session.close()


def test_list_reports_ordered_by_creation() -> None:
    session = _session()
    owner = _register_user(session)
    project = _create_project(session, owner)

    try:
        from app.services.assessments import list_reports

        first = create_report(session, project.id, ReportCreate(title="First"), owner)
        second = create_report(session, project.id, ReportCreate(title="Second"), owner)

        reports = list_reports(session, project.id, owner)
        ids = [r.id for r in reports]
        assert first.id in ids
        assert second.id in ids
        assert all(isinstance(r, Report) for r in reports)
    finally:
        session.delete(project)
        session.commit()
        session.close()

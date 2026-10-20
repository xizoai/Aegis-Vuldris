"""Report generation pipeline for Aegis Vuldris assessments.

Generates shareable report artifacts (JSON, Markdown) from execution
findings, evidence, and risk scores. Reports are written to a configured
output directory and the path is stored on the Report model.
"""

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ProjectNotFoundError
from app.models.evidence import Evidence
from app.models.execution import Execution
from app.models.finding import Finding, FindingConfirmation
from app.models.project import Project
from app.models.report import Report
from app.models.test import SecurityTest
from app.models.user import User
from app.services.projects import ensure_project_access
from app.services.regression import diff_findings
from app.services.report_exporters import find_third_party_exporter
from app.services.risk_scoring import (
    OWASP_LLM_TOP_10_VERSION,
    compute_risk_level,
    compute_risk_score,
    execution_result_label,
    extract_test_category,
    map_category_to_compliance,
    map_category_to_owasp,
    severity_to_score,
)

DEFAULT_REPORT_DIR = Path(os.environ.get("AEGIS_REPORT_DIR", "/tmp/aegis/reports"))


def _report_dir(report_dir: Path | None = None) -> Path:
    base = report_dir or DEFAULT_REPORT_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def _count_by_severity(findings: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = f["severity"].lower()
        counts[sev] = counts.get(sev, 0) + 1
    return counts


_FRAMEWORK_LABELS = {
    "nist_ai_rmf": "NIST AI RMF",
    "eu_ai_act": "EU AI Act",
    "iso_iec_42001": "ISO/IEC 42001",
}


def _collect_report_data(
    session: Session,
    report: Report,
) -> dict:
    """Gather all data needed for a report from the database."""

    project = session.get(Project, report.project_id)
    executions = list(
        session.scalars(
            select(Execution)
            .where(Execution.project_id == report.project_id)
            .order_by(Execution.created_at)
        ).all()
    )

    finding_records: list[Finding] = []
    findings_data: list[dict] = []

    for execution in executions:
        test = session.get(SecurityTest, execution.test_id) if execution.test_id else None
        test_config = test.config if test else {}
        category = extract_test_category(test_config) if test_config else None
        owasp = map_category_to_owasp(category)

        exec_findings = list(
            session.scalars(
                select(Finding)
                .where(Finding.execution_id == execution.id)
                .order_by(Finding.created_at)
            ).all()
        )

        for finding in exec_findings:
            finding_records.append(finding)
            evidence = list(
                session.scalars(
                    select(Evidence)
                    .where(Evidence.finding_id == finding.id)
                    .order_by(Evidence.created_at)
                ).all()
            )
            findings_data.append(
                {
                    "id": str(finding.id),
                    "title": finding.title,
                    "description": finding.description,
                    "severity": finding.severity.value,
                    "severity_score": severity_to_score(finding.severity),
                    "status": finding.status.value,
                    "confirmation": finding.confirmation.value,
                    "confirmation_source": finding.confirmation_source,
                    "disposition_reason": finding.disposition_reason,
                    "details": finding.details,
                    "owasp_category": owasp or "N/A",
                    "compliance_crosswalk": map_category_to_compliance(category),
                    "test_category": category or "unknown",
                    "evidence": [
                        {
                            "id": str(e.id),
                            "kind": e.kind,
                            "description": e.description,
                            "content": e.content,
                            "created_at": e.created_at.isoformat(),
                        }
                        for e in evidence
                    ],
                }
            )

    # Dismissed findings are human-reviewed false positives: they stay in the
    # finding list for the record, but they do not contribute to risk. Anything
    # not dismissed (confirmed or still a candidate) does, because an
    # unconfirmed match is not evidence of safety.
    risk_findings = [
        finding
        for finding in finding_records
        if finding.confirmation != FindingConfirmation.DISMISSED
    ]
    risk_score = compute_risk_score(risk_findings)
    risk_level = compute_risk_level(risk_findings)

    return {
        "report_id": str(report.id),
        "project_id": str(report.project_id),
        "project_name": project.name if project else "unknown",
        "executions": [
            {
                "id": str(e.id),
                "test_id": str(e.test_id) if e.test_id else None,
                "target_id": str(e.target_id) if e.target_id else None,
                "status": e.status.value,
                "result": e.result.value,
                "result_label": execution_result_label(e.result),
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "error": e.error,
                # Snapshot of the target/model profile and test definition used
                # for this run. Null for executions that predate manifests.
                "run_manifest": e.run_manifest,
            }
            for e in executions
        ],
        "findings": findings_data,
        "risk_score": risk_score,
        "risk_level": risk_level.value,
        "total_findings": len(findings_data),
        "findings_by_severity": _count_by_severity(findings_data),
        "owasp_llm_top_10_version": OWASP_LLM_TOP_10_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        # Overwritten by generate_report() with the assigned version number.
        "report_version": 0,
    }


def generate_report(
    session: Session,
    report: Report,
    report_dir: Path | None = None,
    baseline_report_id: UUID | None = None,
) -> str:
    """Generate a report artifact and store its path on the Report.

    Supports ``json`` and ``markdown`` formats. Returns the file path.

    With ``baseline_report_id`` the artifact also carries a "changes since
    baseline" section: the same diff the comparison endpoint and the CLI
    regression gate produce, embedded so a reader sees regressions in
    context. The baseline must be a generated report in the same project;
    callers are responsible for having authorized access to both reports.
    """
    data = _collect_report_data(session, report)

    if baseline_report_id is not None:
        baseline_data = load_report_snapshot(session, baseline_report_id, report.project_id)
        data["changes_since_baseline"] = {
            "baseline_report_id": str(baseline_report_id),
            **diff_findings(baseline_data.get("findings", []), data.get("findings", [])),
        }

    out_dir = _report_dir(report_dir)

    ext = report.format.lower() if report.format else "json"

    # Built-in formats cover JSON and Markdown; anything else must come from a
    # discovered report exporter (aegis.report_exporters entry points).
    # Refusing an unknown format is deliberate: silently rendering "csv" as
    # JSON would hand the user a file whose name lies about its content.
    third_party_exporter = None
    if ext not in ("json", "md", "markdown"):
        third_party_exporter = find_third_party_exporter(ext)
        if third_party_exporter is None:
            raise ValueError(
                f"unsupported report format {ext!r}: no built-in exporter and none "
                "provided by a aegis.report_exporters plugin (see docs/extension-points.md)"
            )

    report.version += 1
    data["report_version"] = report.version

    token = secrets.token_hex(4)
    base = f"report_{report.id}_v{report.version}_{token}"

    # The machine-readable snapshot is always written, so that report-to-report
    # comparison can read a historical run even after findings have changed.
    snapshot_path = out_dir / f"{base}.data.json"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # The shareable artifact is the snapshot itself for JSON, a rendered
    # document for Markdown, or whatever a third-party exporter produces.
    if third_party_exporter is not None:
        filepath = third_party_exporter.write_artifact(data, out_dir)
    elif ext == "json":
        filepath = snapshot_path
    else:
        filepath = out_dir / f"{base}.md"
        _write_markdown_report(filepath, data)

    report.path = str(filepath)
    report.data_path = str(snapshot_path)
    report.generated_at = datetime.now(UTC)
    report.updated_at = datetime.now(UTC)
    session.commit()

    return str(filepath)


def _write_markdown_report(filepath: Path, data: dict) -> None:
    """Write a Markdown-formatted report from collected data."""

    lines: list[str] = []

    lines.append("# Security Assessment Report")
    lines.append("")
    lines.append(f"**Project:** {data['project_name']} (`{data['project_id']}`)")
    lines.append(f"**Generated:** {data['generated_at']}")
    lines.append(f"**Version:** {data['report_version']}")
    lines.append("")

    lines.append("## Risk Summary")
    lines.append("")
    lines.append(f"- **Risk Score:** {data['risk_score']}")
    lines.append(f"- **Risk Level:** {data['risk_level']}")
    lines.append(f"- **Total Findings:** {data['total_findings']}")
    lines.append(
        f"- **OWASP Framework:** GenAI LLM Top 10 {data.get('owasp_llm_top_10_version', '2026')}"
    )
    confirmed = sum(1 for f in data["findings"] if f["confirmation"] == "confirmed")
    candidates = sum(1 for f in data["findings"] if f["confirmation"] == "candidate")
    dismissed = sum(1 for f in data["findings"] if f["confirmation"] == "dismissed")
    lines.append(
        f"- **Confirmation:** {confirmed} confirmed, {candidates} unconfirmed "
        f"(candidates), {dismissed} dismissed as false positives"
    )
    lines.append("- **Findings by Severity:**")
    for sev, count in data["findings_by_severity"].items():
        lines.append(f"  - {sev.capitalize()}: {count}")
    lines.append("")

    lines.append("## Executions")
    lines.append("")
    lines.append("| ID | Result | Status | Started | Error |")
    lines.append("|---|---|---|---|---|")
    for exe in data["executions"]:
        started = exe["started_at"] or "—"
        error = exe["error"] or "—"
        lines.append(
            f"| `{exe['id'][:8]}` | {exe['result_label']} | {exe['status']} | {started} | {error} |"
        )
    lines.append("")

    manifest_executions = [
        exe for exe in data["executions"] if isinstance(exe.get("run_manifest"), dict)
    ]
    if manifest_executions:
        lines.append("## Model and Test Manifests")
        lines.append("")
        lines.append(
            "Each run records the target/model profile and a digest of the test "
            "definition that produced it. The model row can change later; this "
            "snapshot is what makes the result reproducible."
        )
        lines.append("")
        for exe in manifest_executions:
            manifest = exe["run_manifest"]
            target = manifest.get("target") or {}
            test = manifest.get("test") or {}
            generation = manifest.get("effective_generation") or {}
            lines.append(f"### Execution `{exe['id'][:8]}`")
            lines.append("")
            lines.append(f"- **Target:** {target.get('name', '—')} (`{target.get('id', '—')}`)")
            lines.append(f"- **Provider:** {target.get('provider', '—')}")
            lines.append(
                f"- **Model:** {target.get('model') or '—'} "
                f"(version: {target.get('model_version') or 'not declared'})"
            )
            lines.append(f"- **Endpoint:** {target.get('endpoint', '—')}")
            lines.append(
                "- **Effective generation:** "
                + ", ".join(
                    f"{key}={value}" for key, value in generation.items() if value is not None
                )
            )
            lines.append(f"- **Test:** {test.get('name', '—')} (`{test.get('id', '—')}`)")
            lines.append(f"- **Test config SHA-256:** `{test.get('config_sha256', '—')}`")
            lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not data["findings"]:
        lines.append("No findings reported.")
        lines.append("")
    else:
        lines.append("| Title | Severity | Confirmation | OWASP | Category | Status |")
        lines.append("|---|---|---|---|---|---|")
        for f in data["findings"]:
            lines.append(
                f"| {f['title']} | {f['severity']} | {f['confirmation']} "
                f"| {f['owasp_category']} | {f['test_category']} | {f['status']} |"
            )
        lines.append("")

        for f in data["findings"]:
            lines.append(f"### {f['title']}")
            lines.append("")
            lines.append(f"**Severity:** {f['severity']} (score: {f['severity_score']})")
            confirmation_line = f"**Confirmation:** {f['confirmation']}"
            if f["confirmation_source"]:
                confirmation_line += f" (by {f['confirmation_source']})"
            if f["disposition_reason"]:
                confirmation_line += f" — {f['disposition_reason']}"
            lines.append(confirmation_line)
            lines.append(f"**OWASP Category:** {f['owasp_category']}")
            crosswalk = f.get("compliance_crosswalk") or {}
            for framework, references in crosswalk.items():
                label = _FRAMEWORK_LABELS.get(framework, framework)
                lines.append(f"**{label}:** {'; '.join(references)}")
            lines.append(f"**Test Category:** {f['test_category']}")
            lines.append(f"**Status:** {f['status']}")
            lines.append(f"**Description:** {f['description'] or '—'}")
            if f["details"]:
                lines.append(f"**Details:** `{json.dumps(f['details'])}`")
            if f["evidence"]:
                lines.append("")
                lines.append("**Evidence:**")
                for e in f["evidence"]:
                    lines.append(f"- [{e['kind']}] {e['description'] or ''}")
                    if e["content"]:
                        lines.append("```json")
                        lines.append(json.dumps(e["content"], indent=2))
                        lines.append("```")
            lines.append("")

    baseline = data.get("changes_since_baseline")
    if baseline:
        lines.append("## Changes Since Baseline")
        lines.append("")
        lines.append(f"Baseline report: `{baseline['baseline_report_id']}`")
        lines.append("")
        lines.append(
            f"- **New:** {baseline['new_count']}  "
            f"**Resolved:** {baseline['resolved_count']}  "
            f"**Regressed:** {baseline['regressed_count']}  "
            f"**Improved:** {baseline['improved_count']}  "
            f"**Unchanged:** {baseline['unchanged_count']}"
        )
        lines.append("")
        if baseline["new_findings"]:
            lines.append("**New findings:**")
            for finding in baseline["new_findings"]:
                lines.append(f"- [{finding['severity']}] {finding['title']}")
            lines.append("")
        if baseline["regressed_findings"]:
            lines.append("**Regressed findings** (severity increased):")
            for entry in baseline["regressed_findings"]:
                lines.append(
                    f"- [{entry['severity_before']} → {entry['severity_after']}] {entry['title']}"
                )
            lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def require_project_report(
    session: Session,
    user: User,
    project_id: UUID,
    report_id: UUID,
) -> Report:
    """Authorize access to a single report and return it.

    Reports carry the full evidence set for an assessment, so every report
    route must confirm both that the report belongs to the given project and
    that the *caller* has access to that project. Checking only the path
    parameter would let anyone holding a project_id and report_id read another
    tenant's prompts and responses.
    """

    report = session.get(Report, report_id)
    if report is None or report.project_id != project_id:
        raise ProjectNotFoundError()

    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError()
    ensure_project_access(session, user, project, "read")
    return report


def get_report_download_path(
    session: Session,
    report_id: UUID,
    project_id: UUID,
) -> Path:
    """Return the file path for a report download, raising if not found."""

    report = session.get(Report, report_id)
    if report is None or report.project_id != project_id:
        raise FileNotFoundError(f"report {report_id} not found")
    if not report.path:
        raise FileNotFoundError("report has not been generated yet")
    path = Path(report.path)
    if not path.exists():
        raise FileNotFoundError(f"report file not found: {path}")
    return path


def load_report_snapshot(
    session: Session,
    report_id: UUID,
    project_id: UUID,
) -> dict:
    """Load a report's persisted JSON data snapshot.

    Comparison reads the stored snapshot rather than live database state so
    that two historical runs can be compared even after the underlying
    findings and executions have changed.
    """

    report = session.get(Report, report_id)
    if report is None or report.project_id != project_id:
        raise FileNotFoundError(f"report {report_id} not found")

    if not report.data_path:
        raise FileNotFoundError("report has no data snapshot; generate it first")

    path = Path(report.data_path)
    if not path.exists():
        raise FileNotFoundError(f"report data snapshot not found: {path}")

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compare_reports(
    session: Session,
    report_a_id: UUID,
    report_b_id: UUID,
    project_id: UUID,
) -> dict:
    """Compare two report runs and return new/resolved/regressed findings.

    Both reports must belong to the supplied project and must have been
    generated (so that a data snapshot exists). Findings are matched by
    their ``(test_category, title)`` key. A finding present in B but not A
    is "new"; present in A but not B is "resolved"; present in both but
    with a higher severity in B is "regressed" (and lower severity in B is
    "improved").

    The classification itself lives in ``services/regression.py`` so the
    API comparison and the CLI regression gate share one implementation.
    """

    def _findings(report_id: UUID) -> list[dict]:
        data = load_report_snapshot(session, report_id, project_id)
        return data.get("findings", [])

    diff = diff_findings(_findings(report_a_id), _findings(report_b_id))
    return {
        "report_a_id": str(report_a_id),
        "report_b_id": str(report_b_id),
        **diff,
    }


__all__ = [
    "DEFAULT_REPORT_DIR",
    "compare_reports",
    "generate_report",
    "get_report_download_path",
    "load_report_snapshot",
]

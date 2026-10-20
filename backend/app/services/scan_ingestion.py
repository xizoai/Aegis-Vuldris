"""Map external tool verdicts into Aegis findings.

One ingestion framework, two producers: garak (phase 2) and PyRIT (phase 3)
both reduce a run to :class:`~app.schemas.scan.ScanResultRecord` values and both
land here, so severity, OWASP mapping, and the shape of a scan finding are
decided once rather than per tool.

Only failures become findings. A probe that was refused produced no issue, and
recording it would bury the failures in noise; the pass count is reported back
to the caller for accounting. A verdict of ``inconclusive`` is also not a
finding -- it is a tool error, and the plan forbids reporting it as a pass.

Findings deliberately do not carry prompts or model output. That content stays
in the raw tool report under the retention-managed report volume, which is
where the sensitive material belongs (plan section 4.6, open question 3); a
finding keeps the identifiers and the count needed to find the record again.
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.external_scan import ExternalScan
from app.models.finding import Finding
from app.schemas.scan import ScanResultRecord
from app.services.risk_scoring import map_category_to_owasp
from app.services.severity_scorer import compute_automatic_severity

# Probe family (the part of a garak probe id before the first dot) to a category
# key understood by ``OWASP_LLM_TOP_10``. Families with no LLM Top 10 entry are
# mapped to None rather than forced into an unrelated one.
PROBE_FAMILIES: Final[dict[str, str | None]] = {
    "dan": "jailbreak",
    "promptinject": "prompt_injection",
    "encoding": "prompt_injection",
    "goodside": "prompt_injection",
    "continuation": "prompt_injection",
    "snowball": "prompt_injection",
    "atkgen": "prompt_injection",
    "leakreplay": "privacy_data_leakage",
    "realtoxicityprompts": None,
    "lmrc": None,
    "malwaregen": None,
    "xss": None,
    "knownbadsignatures": None,
    "packagehallucination": None,
}

# Human-readable labels, used in finding text. The severity scorer reads this
# text, so the label is what turns a category into a severity tier; the strings
# are chosen to hit the existing keyword signals rather than to be pretty.
CATEGORY_LABELS: Final[dict[str, str]] = {
    "prompt_injection": "prompt injection",
    "jailbreak": "jailbreak",
    "privacy_data_leakage": "data leakage",
    "rag_attack": "retrieval poisoning",
    "agent_tool_use": "unsafe agent tool use",
}


@dataclass(frozen=True)
class IngestSummary:
    """What one ingestion pass produced."""

    failures: int = 0
    passes: int = 0
    inconclusive: int = 0

    @property
    def findings(self) -> int:
        return self.failures


def probe_family(probe: str) -> str:
    """Return the probe family of a garak-style probe id."""

    return probe.split(".", 1)[0].strip().lower()


def category_for_probe(probe: str, reported: str | None = None) -> str | None:
    """Return the category for a probe, preferring what the tool reported."""

    if reported:
        return reported.strip().lower()
    return PROBE_FAMILIES.get(probe_family(probe))


def build_scan_finding(scan: ExternalScan, record: ScanResultRecord) -> Finding:
    """Build the finding for one failed verdict.

    Severity comes from the shared scorer, not from the tool: garak has no
    severity, and letting a probe's own name decide a tier would make scan
    findings sort differently from native ones for the same weakness.
    """

    category = category_for_probe(record.probe, record.category)
    label = CATEGORY_LABELS.get(category or "", None)
    detector = record.detector or "an unnamed detector"

    description_parts = [f"External scan: {label}." if label else "External scan."]
    description_parts.append(f"Probe {record.probe} produced a response that failed {detector}.")
    if record.trigger_count:
        description_parts.append(
            f"{record.trigger_count} triggering string(s); the content is in the raw report."
        )
    if record.notes:
        description_parts.append(f"Tool note: {record.notes}")

    details: dict[str, object] = {
        "source": "external_scan",
        "tool": scan.tool.value,
        "probe": record.probe,
        "trigger_count": record.trigger_count,
    }
    for key, value in (
        ("tool_version", scan.tool_version),
        ("detector", record.detector),
        ("category", category),
        ("owasp", map_category_to_owasp(category)),
        ("record_index", record.record_index),
        ("report_path", scan.report_path),
    ):
        if value is not None:
            details[key] = value

    finding = Finding(
        external_scan_id=scan.id,
        title=f"{scan.tool.value} probe {record.probe} was not refused"[:200],
        description=" ".join(description_parts)[:1000],
        details=details,
    )
    finding.severity = compute_automatic_severity(finding)
    return finding


def ingest_scan_results(
    session: Session,
    scan: ExternalScan,
    results: list[ScanResultRecord],
) -> IngestSummary:
    """Replace a scan's findings with those derived from its results.

    Re-ingesting the same scan is a no-op rather than a duplicate: the scan's
    previous findings are removed first. Completing a scan is already
    exactly-once, so this is a second line of defence, but it also makes a
    manual re-ingest (for example after a tool-version bump) well defined.

    The caller owns the transaction. This does not commit, so a failure here
    rolls back with the scan's terminal transition rather than leaving a
    completed scan with half its findings.
    """

    session.execute(delete(Finding).where(Finding.external_scan_id == scan.id))

    failures = 0
    passes = 0
    inconclusive = 0

    for record in results:
        if record.verdict == "fail":
            failures += 1
            session.add(build_scan_finding(scan, record))
        elif record.verdict == "pass":
            passes += 1
        else:
            inconclusive += 1

    session.flush()

    return IngestSummary(
        failures=failures,
        passes=passes,
        inconclusive=inconclusive,
    )


__all__ = [
    "CATEGORY_LABELS",
    "PROBE_FAMILIES",
    "IngestSummary",
    "build_scan_finding",
    "category_for_probe",
    "ingest_scan_results",
    "probe_family",
]

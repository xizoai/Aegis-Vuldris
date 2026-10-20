"""External scan API schemas for AegisAI."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.external_scan import ExternalScanStatus, ExternalScanTool


class ScanCreate(BaseModel):
    """Request schema for queueing an external scan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_id: UUID
    tool: ExternalScanTool
    # Tool selection and limits. Deliberately opaque to the API: the runner
    # interprets it, while the API records it so a scan is attributable and
    # reproducible. Bounded at write time by the request size limit.
    config: dict[str, Any] = Field(default_factory=dict)


class ScanResultRecord(BaseModel):
    """One normalized tool verdict the runner reports for a claimed scan.

    Deliberately content-free: a probe id, the detector that judged it, and the
    verdict. The prompt and the model's response stay in the raw report the
    runner writes to its volume -- they are attack content, and when a probe
    works they are the very data the finding is about, so they are not copied
    into the database (plan section 4.6, open question 3). A count is reported
    instead of the flagged strings.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    probe: str = Field(min_length=1, max_length=200)
    detector: str | None = Field(default=None, max_length=200)
    verdict: Literal["pass", "fail", "inconclusive"]
    # A coarse family for OWASP mapping, e.g. "prompt_injection". Optional
    # because not every tool names one.
    category: str | None = Field(default=None, max_length=100)
    # How many strings the detector flagged, not the strings themselves.
    trigger_count: int = Field(default=0, ge=0)
    # Tool-generated diagnostic (a detector error, a provider timeout). Never
    # model output.
    notes: str | None = Field(default=None, max_length=500)
    # Position in the raw report, so a finding can be traced back to its record.
    record_index: int | None = Field(default=None, ge=0)


# A scan is a bounded batch, but a probe family can emit many attempts. The cap
# keeps one completion report from becoming an unbounded write; a tool that
# exceeds it fails loudly instead of being silently truncated.
_MAX_SCAN_RESULTS = 2000


class ScanCompleteRequest(BaseModel):
    """Runner's terminal report for a claimed scan.

    Results ride along with the terminal state so the runner makes exactly one
    call to finish a scan: there is no window where a scan is completed with no
    findings and no second call to lose. The completion guard still applies, so
    a retry after a lost reply is a conflict rather than a duplicate ingest.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed"]
    tool_version: str | None = Field(default=None, max_length=100)
    external_run_id: str | None = Field(default=None, max_length=255)
    report_path: str | None = Field(default=None, max_length=1024)
    error: str | None = Field(default=None, max_length=4000)
    results: list[ScanResultRecord] = Field(
        default_factory=list,
        max_length=_MAX_SCAN_RESULTS,
    )


class ScanResponse(BaseModel):
    """Response schema for an external scan."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )

    id: UUID
    project_id: UUID
    target_id: UUID | None
    tool: ExternalScanTool
    tool_version: str | None
    config: dict[str, Any]
    status: ExternalScanStatus
    external_run_id: str | None
    report_path: str | None
    created_by: UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    claimed_at: datetime | None
    attempt_count: int
    # Counted, not logged: the shim's volume surface, visible without pulling
    # prompt or response bodies into any response.
    forwarded_requests: int = 0
    error: str | None


class ScanClaimResponse(BaseModel):
    """A runner claim. ``scan`` is null when the queue is empty.

    ``llm_token`` carries the scan-scoped token the shim accepts. It is minted
    per claim, so it exists only while this claim is active, and it binds one
    target for one scan -- the runner never sees a project-wide credential.
    """

    model_config = ConfigDict(extra="forbid")

    scan: ScanResponse | None
    llm_token: str | None = None


__all__ = [
    "ScanClaimResponse",
    "ScanCompleteRequest",
    "ScanCreate",
    "ScanResponse",
    "ScanResultRecord",
]

"""Assessment domain schemas for Aegis Vuldris."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.execution import ExecutionResult, ExecutionStatus
from app.models.finding import FindingConfirmation, FindingSeverity, FindingStatus
from app.schemas.test_case import TestCaseCategory


class SeedReportLike(Protocol):
    """Structural type for the result of a seeding run."""

    created: list[str]
    skipped: list[str]
    invalid: dict[str, str]


class SecurityTestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    provider: str = Field(min_length=1, max_length=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)


class SecurityTestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    provider: str | None = Field(default=None, min_length=1, max_length=100)
    required_capabilities: list[str] | None = Field(default=None, max_length=50)
    config: dict[str, Any] | None = None


class SecurityTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None
    provider: str
    required_capabilities: list[str]
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: UUID | None = None
    target_id: UUID | None = None


class BulkExecutionCreate(BaseModel):
    """Request schema for running many tests against one target.

    Selecting tests one at a time is not a realistic workflow for a suite of 224.
    Every listed test must belong to the project; the target must be usable. A
    run that cannot proceed at all returns an error rather than a partial
    result the caller might misread as complete.
    """

    model_config = ConfigDict(extra="forbid")

    # Leave headroom above the current 224-case bundled library while keeping a
    # bounded request size for the in-process runner.
    test_ids: list[UUID] = Field(min_length=1, max_length=250)
    target_id: UUID


class BulkExecutionAccepted(BaseModel):
    """Acknowledgement that a bulk run was queued.

    Deliberately not the result. Running 224 tests against a local model takes
    minutes, and nginx caps a single request at 300s, so waiting for the whole
    run inside the request would truncate it. The caller polls the executions it
    already polls, keyed by ``test_id``.
    """

    model_config = ConfigDict(extra="forbid")

    total: int
    target_id: UUID
    execution_ids: list[UUID]


class BulkExecutionResult(BaseModel):
    """Per-test outcome within a bulk run."""

    model_config = ConfigDict(extra="forbid")

    test_id: UUID | None
    test_name: str
    execution_id: UUID | None = None
    status: str
    result: str | None = None
    error: str | None = None
    finding_count: int = 0


class BulkExecutionResponse(BaseModel):
    """Summary of one bulk run."""

    model_config = ConfigDict(extra="forbid")

    total: int
    queued: int
    completed: int
    failed: int
    results: list[BulkExecutionResult]


class ExecutionUpdate(BaseModel):
    """Request schema for updating an execution.

    Deliberately carries no fields. Execution status and result are owned by
    the execution engine: they are the assessment's verdict, and a client that
    could set them could mark a failed run as ``succeeded``/``pass`` and hide a
    real finding. Transitions happen only through run, cancel, and the engine
    itself.
    """

    model_config = ConfigDict(extra="forbid")


class ExecutionFindingSummary(BaseModel):
    """The finding that explains a failed result.

    An execution that succeeded with result ``fail`` carries no ``error``:
    the reason lives in the finding its grader produced — the matched patterns,
    the response excerpt. Without this the executions table would show nothing
    for exactly the rows a user cares about most.

    ``confirmation`` is carried so a ``needs_review`` row can say why it is
    not a ``fail``: the finding is still a candidate, not an established
    vulnerability.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    title: str
    description: str | None
    severity: FindingSeverity
    status: FindingStatus
    confirmation: FindingConfirmation = FindingConfirmation.CANDIDATE


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    test_id: UUID | None
    target_id: UUID | None
    status: ExecutionStatus
    result: ExecutionResult
    started_at: datetime | None
    completed_at: datetime | None
    # Why the execution failed, when it did. Without this the UI could only
    # report "failed", which is indistinguishable between a misconfigured
    # target, a bad credential, and a provider outage.
    error: str | None = None
    # Why the test failed, when the attack landed: the finding its grader
    # produced. Infrastructure failures use ``error`` instead.
    finding_summary: ExecutionFindingSummary | None = None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    # Set when this execution is a verification run for a finding.
    verifies_finding_id: UUID | None = None
    # Immutable snapshot of the target/model profile and test definition used
    # for this run. Older executions predate manifests and return null.
    run_manifest: dict[str, Any] | None = None


class ExecutionStepResponse(BaseModel):
    """One conversational turn of an execution, as recorded.

    This is the transcript: the exact request content (messages, model,
    parameters, converters applied) and the response the target returned.
    Content is redacted on read with the same detector used for stored
    evidence, because the transcript of a data-leakage attempt is exactly
    where leaked secrets would otherwise appear in full.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    execution_id: UUID
    turn_number: int
    request_content: dict[str, Any]
    response_output: str | None
    status: str
    error: str | None = None
    created_at: datetime
    # Whether sensitive values were replaced in this turn's content.
    redacted: bool = False
    detected_kinds: list[str] = Field(default_factory=list)
    sensitivity: int = 0


class FindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    execution_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    severity: FindingSeverity = FindingSeverity.MEDIUM
    details: dict[str, Any] = Field(default_factory=dict)


class FindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FindingStatus | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _reject_verified_status(cls, value: FindingStatus | None) -> FindingStatus | None:
        """``verified`` is evidence, not an editable state.

        If a client could set it, the word would degrade into another way of
        saying "fixed" and the platform would claim proven fixes it never
        checked.
        """

        if value == FindingStatus.VERIFIED:
            raise ValueError(
                "status 'verified' is set only by a passed verification run; "
                "mark the finding 'fixed' and verify it instead"
            )
        return value


class FindingTriageRequest(BaseModel):
    """Request schema for the confirmation stage of triage.

    Separate from ``FindingUpdate`` because it changes the verdict, not the
    label: it records whether the observed attack result is real. A
    dismissal is a false-positive claim, so it must carry a reason — an
    unexplained dismissal would make the precision metric meaningless.
    Severity may be corrected in the same action; a severity override also
    requires a reason for the same reason.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    confirmation: FindingConfirmation
    reason: str | None = Field(default=None, max_length=500)
    severity: FindingSeverity | None = None

    def require_reason(self, original_severity: FindingSeverity) -> None:
        """Validate cross-field rules the field validators cannot see."""

        if self.confirmation == FindingConfirmation.DISMISSED and not self.reason:
            raise ValueError("a reason is required to dismiss a finding as a false positive")
        if self.severity is not None and self.severity != original_severity and not self.reason:
            raise ValueError("a reason is required to override a finding's severity")


class FindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    # Exactly one of these two origins is set: a native execution or an
    # external scan. Both are nullable so one model serves both.
    execution_id: UUID | None
    external_scan_id: UUID | None = None
    title: str
    description: str | None
    severity: FindingSeverity
    status: FindingStatus
    details: dict[str, Any]
    confirmation: FindingConfirmation = FindingConfirmation.CANDIDATE
    confirmation_source: str | None = None
    disposition_reason: str | None = None
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class VerificationCreate(BaseModel):
    """Request schema for re-running the exact attack behind a finding.

    ``target_id`` optionally verifies against a different target in the same
    project, for example a fixed staging deployment. With no target, the
    original target is re-used.
    """

    model_config = ConfigDict(extra="forbid")

    target_id: UUID | None = None


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    finding_id: UUID
    kind: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    content: dict[str, Any] = Field(default_factory=dict)


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    finding_id: UUID
    kind: str
    description: str | None
    content: dict[str, Any]
    # What sensitive data this evidence was found to contain.
    sensitivity: int
    detected_kinds: list[str]
    redacted: int
    created_at: datetime


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    format: str = Field(default="json", min_length=1, max_length=20)


class ReportGenerateRequest(BaseModel):
    """Request schema for generating (or regenerating) a report artifact.

    ``baseline_report_id`` optionally names a previously generated report in
    the same project; the artifact then carries a "changes since baseline"
    section produced by the shared regression diff.
    """

    model_config = ConfigDict(extra="forbid")

    baseline_report_id: UUID | None = None


class TestSeedRequest(BaseModel):
    """Request schema for loading the bundled security test library."""

    model_config = ConfigDict(extra="forbid")

    category: list[TestCaseCategory] = Field(
        default_factory=list,
        description="Restrict seeding to these categories. Empty means all.",
    )


class TestSeedResponse(BaseModel):
    """Response schema describing the outcome of a library seed."""

    model_config = ConfigDict(extra="forbid")

    created: int
    skipped: int
    invalid: int
    total: int

    @classmethod
    def from_report(cls, report: "SeedReportLike") -> "TestSeedResponse":
        """Build a response from a seed report.

        Takes a structural type so the schema layer does not import the
        service layer.
        """

        created = len(report.created)
        skipped = len(report.skipped)
        invalid = len(report.invalid)
        return cls(
            created=created,
            skipped=skipped,
            invalid=invalid,
            total=created + skipped + invalid,
        )


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    project_id: UUID
    title: str
    format: str
    path: str
    version: int = 1
    generated_at: datetime | None = None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class ReportComparisonResponse(BaseModel):
    """Result of comparing two report runs."""

    model_config = ConfigDict(extra="forbid")

    report_a_id: UUID
    report_b_id: UUID
    new_count: int = 0
    resolved_count: int = 0
    regressed_count: int = 0
    improved_count: int = 0
    unchanged_count: int = 0
    new_findings: list[dict[str, Any]] = Field(default_factory=list)
    resolved_findings: list[dict[str, Any]] = Field(default_factory=list)
    regressed_findings: list[dict[str, Any]] = Field(default_factory=list)
    improved_findings: list[dict[str, Any]] = Field(default_factory=list)
    unchanged_findings: list[dict[str, Any]] = Field(default_factory=list)


class TestTriageStats(BaseModel):
    """Per-test triage outcome, the feedback signal for the library.

    ``dismissed_rate`` is the share of this test's findings that reviewers
    rejected as false positives. A test whose matches are mostly dismissed is
    a noisy detector: its patterns need tightening, not its score celebrated.
    """

    model_config = ConfigDict(extra="forbid")

    test_id: UUID
    test_name: str
    category: str | None = None
    findings: int = 0
    confirmed: int = 0
    candidate: int = 0
    dismissed: int = 0
    dismissed_rate: float = 0.0

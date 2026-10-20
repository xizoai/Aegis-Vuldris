"""Remediation and candidate patch schemas for Aegis Vuldris.

These schemas cover AutoFix's review-only stages: the deterministic
remediation plan and the candidate patch proposals drafted from it. None of
them can change a finding's fix state.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.patch_proposal import PatchApproach, PatchProposalMode


class RemediationPlanResponse(BaseModel):
    """A review-only AutoFix recommendation for a finding.

    Suggestions never apply a patch or alter the finding state. A later,
    isolated remediation runner may attach validation evidence before a human
    can approve an applied change.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    finding_id: UUID
    category: str | None
    kind: str
    root_cause_hypothesis: str
    recommendations: list[str]
    verification_steps: list[str]
    limitations: list[str]
    attack_id: str | None
    attack_version: str | None
    template_version: str
    status: str
    autonomy: str
    patch_available: bool
    requires_human_approval: bool


class PatchProposalCreate(BaseModel):
    """Request to draft a candidate patch for a finding.

    With ``drafting_target_id``, the named OpenAI-compatible or Ollama target
    in the same project drafts a unified diff from the explicitly supplied
    file content. Without it, a deterministic template-mode proposal is
    recorded and no model is called; supplying file content is optional and
    ignored in that case.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_path: str | None = Field(default=None, min_length=1, max_length=500)
    file_content: str | None = Field(default=None, min_length=1, max_length=100_000)
    drafting_target_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_file_requirements(self) -> "PatchProposalCreate":
        """Keep the file pair honest and require it when a model drafts."""

        if (self.file_path is None) != (self.file_content is None):
            raise ValueError("file_path and file_content must be supplied together")
        if self.drafting_target_id is not None and self.file_path is None:
            raise ValueError(
                "a drafting model needs the file to patch: supply file_path and file_content"
            )
        return self


class PatchProposalResponse(BaseModel):
    """A stored, review-only candidate patch.

    ``diff_text`` is NULL for template-mode proposals, which stay advisory
    rather than fabricating a diff. A proposal never proves anything: the
    finding is verified only by a passed verification rerun after a human
    applies and claims the change.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    finding_id: UUID
    mode: PatchProposalMode
    approach: PatchApproach
    rationale: str
    diff_text: str | None
    files_touched: list[str]
    prompt_hash: str | None
    template_version: str | None
    drafting_target_id: UUID | None
    drafting_model: str | None
    created_by: UUID | None
    created_at: datetime

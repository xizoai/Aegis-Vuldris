"""Deterministic, review-only remediation planning for security findings.

This is the safe first stage of AutoFix. It turns a finding into an auditable
suggestion and verification plan, but never edits source code, calls an LLM, or
marks a finding fixed. Applying a patch belongs to a later, isolated workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.errors import AssessmentNotFoundError, ProjectNotFoundError
from app.models.execution import Execution
from app.models.finding import Finding
from app.models.test import SecurityTest
from app.models.user import User
from app.services.assessments import require_finding_read


@dataclass(frozen=True)
class RemediationTemplate:
    """A deterministic mapping from a tested risk area to safer controls."""

    kind: str
    root_cause: str
    recommendations: tuple[str, ...]
    verification_steps: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class RemediationPlan:
    """A reviewable suggestion; it is deliberately not an applied fix."""

    finding_id: UUID
    category: str | None
    kind: str
    root_cause_hypothesis: str
    recommendations: tuple[str, ...]
    verification_steps: tuple[str, ...]
    limitations: tuple[str, ...]
    attack_id: str | None
    attack_version: str | None
    template_version: str = "1.0.0"
    status: str = "suggested"
    autonomy: str = "suggest"
    patch_available: bool = False
    requires_human_approval: bool = True


_DEFAULT_TEMPLATE = RemediationTemplate(
    kind="manual_review",
    root_cause=(
        "The available evidence does not identify a safe automatic remediation; "
        "an operator must inspect the affected control boundary."
    ),
    recommendations=(
        "Review the finding evidence and the affected application boundary.",
        "Choose the smallest control change that enforces the intended security property.",
    ),
    verification_steps=(
        "Rerun the original security test after the reviewed change.",
        "Run the relevant authorization, data-handling, and regression tests.",
    ),
    limitations=("This suggestion does not diagnose source code or apply a patch.",),
)

_TEMPLATES: dict[str, RemediationTemplate] = {
    "prompt_injection": RemediationTemplate(
        kind="hybrid",
        root_cause=(
            "Untrusted input may be able to influence trusted instructions or downstream actions."
        ),
        recommendations=(
            "Keep trusted instructions and untrusted content in separate, typed fields.",
            "Enforce authorization, tool policy, and sensitive-data boundaries outside the model.",
            "Treat retrieved or user-provided instructions as data, not executable policy.",
        ),
        verification_steps=(
            "Rerun this exact prompt-injection attack using the same attack ID and version.",
            "Run neighboring injection and jailbreak cases before approving a change.",
            "Confirm prohibited tool calls and protected-data access remain blocked server-side.",
        ),
        limitations=(
            "A stronger system prompt alone is not sufficient evidence that the boundary is fixed.",
        ),
    ),
    "jailbreak": RemediationTemplate(
        kind="llm_behavior",
        root_cause=(
            "The model-facing policy can be bypassed by conflicting or obfuscated instructions."
        ),
        recommendations=(
            "Define the prohibited behavior as an enforceable policy outside the model "
            "where possible.",
            "Add output validation and action allowlists for any sensitive downstream operation.",
            "Use the failed case as a regression example for the supported model configuration.",
        ),
        verification_steps=(
            "Rerun this jailbreak case and related refusal-consistency cases.",
            "Verify the application does not perform a prohibited action even if the model "
            "output changes.",
        ),
        limitations=(
            "External model weights cannot be modified by Aegis; this plan targets usage controls.",
        ),
    ),
    "privacy_data_leakage": RemediationTemplate(
        kind="application",
        root_cause=(
            "Protected data may be present in model context or returned without an "
            "enforced access check."
        ),
        recommendations=(
            "Enforce authorization at the data-retrieval boundary, not only in prompts.",
            "Minimize model context and replace sensitive values with scoped synthetic "
            "canaries in tests.",
            "Redact protected output and logs before storing or displaying them.",
        ),
        verification_steps=(
            "Rerun the canary disclosure or cross-user isolation attack that produced the finding.",
            "Run cross-project and unauthorized-user access tests.",
            "Review evidence storage and logs for the protected value.",
        ),
        limitations=("Rotation of a real exposed credential requires explicit operator action.",),
    ),
    "rag_attack": RemediationTemplate(
        kind="application",
        root_cause=(
            "Retrieval trust, document authorization, or provenance may not be enforced "
            "at query time."
        ),
        recommendations=(
            "Apply document and tenant authorization filters before retrieval results "
            "reach the model.",
            "Attach provenance to retrieved content and keep it separate from trusted "
            "instructions.",
            "Validate citations and reject retrieved instructions that request privileged actions.",
        ),
        verification_steps=(
            "Rerun the same RAG case in a controlled retrieval environment.",
            "Run cross-user, cross-project, and deleted-document retrieval tests.",
        ),
        limitations=(
            "Response-only targets cannot prove retrieval authorization without a "
            "RAG-capable adapter.",
        ),
    ),
    "agent_tool_use": RemediationTemplate(
        kind="application",
        root_cause=(
            "A model-directed tool action may not have independent server-side "
            "authorization or validation."
        ),
        recommendations=(
            "Authorize every tool call against the acting user and resource before execution.",
            "Validate tool arguments with a strict schema and deny unexpected side "
            "effects by default.",
            "Run tools with least privilege and record the approved action and outcome.",
        ),
        verification_steps=(
            "Rerun the tool-use attack with simulated or isolated tools.",
            "Confirm prohibited actions, malformed arguments, and loops are rejected server-side.",
        ),
        limitations=(
            "Do not run destructive verification against production tools or credentials.",
        ),
    ),
}


def build_remediation_plan(
    finding_id: UUID,
    test_config: dict | None,
) -> RemediationPlan:
    """Build a deterministic Level-1 suggestion from validated assessment metadata."""

    config = test_config if isinstance(test_config, dict) else {}
    category_value = config.get("category")
    category = (
        category_value if isinstance(category_value, str) and category_value in _TEMPLATES else None
    )
    attack = config.get("attack")
    attack_data = attack if isinstance(attack, dict) else {}
    attack_id = attack_data.get("id") if isinstance(attack_data.get("id"), str) else None
    attack_version = (
        attack_data.get("version") if isinstance(attack_data.get("version"), str) else None
    )
    template = _TEMPLATES.get(category or "", _DEFAULT_TEMPLATE)

    return RemediationPlan(
        finding_id=finding_id,
        category=category,
        kind=template.kind,
        root_cause_hypothesis=template.root_cause,
        recommendations=template.recommendations,
        verification_steps=template.verification_steps,
        limitations=template.limitations,
        attack_id=attack_id,
        attack_version=attack_version,
    )


def get_remediation_plan(
    session: Session,
    project_id: UUID,
    finding_id: UUID,
    user: User,
) -> RemediationPlan:
    """Authorize and build a plan without exposing evidence or secrets to a model."""

    finding = session.get(Finding, finding_id)
    if finding is None:
        raise AssessmentNotFoundError()
    finding_project_id = require_finding_read(session, finding, user)
    if finding_project_id != project_id:
        raise ProjectNotFoundError()

    execution = (
        session.get(Execution, finding.execution_id) if finding.execution_id is not None else None
    )
    test = (
        session.get(SecurityTest, execution.test_id)
        if execution is not None and execution.test_id is not None
        else None
    )
    return build_remediation_plan(finding.id, test.config if test is not None else None)


__all__ = ["RemediationPlan", "build_remediation_plan", "get_remediation_plan"]

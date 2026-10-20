"""Remediation planning (AutoFix Level 1) service tests.

A remediation plan is a review-only suggestion. These tests pin the
properties that make it safe to expose: it maps each finding category to
its remediation strategy, it carries stable attack identity for a
reproducible verification rerun, and it never claims a patch exists or
that a fix was applied.
"""

from uuid import uuid4

import pytest
from app.api.errors import (
    AssessmentNotFoundError,
    PermissionDeniedError,
    ProjectNotFoundError,
)
from app.db.session import create_session_factory
from app.models.execution import Execution
from app.models.finding import Finding
from app.models.project import Project
from app.models.test import SecurityTest
from app.models.user import User, UserRole
from app.schemas import (
    ExecutionCreate,
    FindingCreate,
    ProjectCreate,
    ProjectMembershipCreate,
    SecurityTestCreate,
    UserCreate,
)
from app.services.assessments import create_execution, create_finding, create_security_test
from app.services.auth import register_user
from app.services.memberships import create_project_membership
from app.services.projects import create_project
from app.services.remediation import get_remediation_plan
from sqlalchemy.orm import Session

# The strategy each tested category must map to. Application fixes stay
# separate from model-behaviour fixes; an unknown category must fall back to
# manual review rather than inventing an automatic fix.
EXPECTED_KINDS = {
    "prompt_injection": "hybrid",
    "jailbreak": "llm_behavior",
    "privacy_data_leakage": "application",
    "rag_attack": "application",
    "agent_tool_use": "application",
}


def _session() -> Session:
    return create_session_factory()()


def _register_user(session: Session, role: UserRole = UserRole.USER) -> User:
    user = register_user(
        session,
        UserCreate(
            email=f"remediation-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )
    if role != UserRole.USER:
        user.role = role
        session.commit()
        session.refresh(user)
    return user


def _create_project(session: Session, owner: User) -> Project:
    return create_project(
        session,
        ProjectCreate(name=f"Remediation Project {uuid4()}"),
        owner_id=owner.id,
    )


def _seed_finding(
    session: Session,
    *,
    config: dict | None = None,
) -> tuple[User, Project, Finding]:
    """Create a project, test, execution, and finding for plan tests.

    Returns ``(owner, project, finding)``. The test config drives the
    template selection, so each caller passes the category it exercises.
    """

    owner = _register_user(session)
    project = _create_project(session, owner)
    test = create_security_test(
        session,
        project.id,
        SecurityTestCreate(
            name=f"Remediation case {uuid4()}",
            provider="openai_compatible",
            config=config or {},
        ),
        owner,
    )
    execution = create_execution(session, project.id, ExecutionCreate(test_id=test.id), owner)
    finding = create_finding(
        session,
        FindingCreate(execution_id=execution.id, title="Assessment finding"),
        owner,
    )
    return owner, project, finding


@pytest.mark.parametrize("category", sorted(EXPECTED_KINDS))
def test_each_category_maps_to_its_remediation_strategy(category: str) -> None:
    session = _session()
    owner, project, finding = _seed_finding(session, config={"category": category})

    try:
        plan = get_remediation_plan(session, project.id, finding.id, owner)

        assert plan.kind == EXPECTED_KINDS[category]
        assert plan.category == category
        # A plan without actionable controls or a verification method is not
        # reviewable, so every template must carry both.
        assert plan.recommendations
        assert plan.verification_steps
        assert plan.limitations
    finally:
        session.delete(project)
        session.commit()
        session.close()


@pytest.mark.parametrize(
    "config",
    [None, {}, {"category": "not_a_real_category"}, {"category": 42}],
)
def test_unknown_or_missing_category_falls_back_to_manual_review(config: dict | None) -> None:
    """No safe automatic change can be established, so the plan says so."""

    session = _session()
    owner, project, finding = _seed_finding(session, config=config)

    try:
        plan = get_remediation_plan(session, project.id, finding.id, owner)

        assert plan.kind == "manual_review"
        assert plan.category is None
        assert plan.recommendations
        assert plan.verification_steps
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_plan_carries_attack_identity_for_reproducible_verification() -> None:
    """The verification rerun must name the exact attack that found this."""

    session = _session()
    owner, project, finding = _seed_finding(
        session,
        config={
            "category": "prompt_injection",
            "attack": {
                "id": "builtin/prompt-injection/01-direct-instruction-override",
                "version": "2.0.0",
            },
        },
    )

    try:
        plan = get_remediation_plan(session, project.id, finding.id, owner)

        assert plan.attack_id == "builtin/prompt-injection/01-direct-instruction-override"
        assert plan.attack_version == "2.0.0"
        assert plan.kind == "hybrid"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_plan_without_attack_metadata_has_no_attack_identity() -> None:
    session = _session()
    owner, project, finding = _seed_finding(session, config={"category": "jailbreak"})

    try:
        plan = get_remediation_plan(session, project.id, finding.id, owner)

        assert plan.attack_id is None
        assert plan.attack_version is None
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_plan_never_claims_a_patch_or_an_applied_fix() -> None:
    """Generating a suggestion is not applying or verifying a fix.

    Every plan must state the suggest-only autonomy level, report that no
    patch exists, and require human approval. This is what stops a later
    change from quietly relabelling suggestions as fixes.
    """

    session = _session()
    owner, project, finding = _seed_finding(session, config={"category": "jailbreak"})

    try:
        plan = get_remediation_plan(session, project.id, finding.id, owner)

        assert plan.status == "suggested"
        assert plan.autonomy == "suggest"
        assert plan.patch_available is False
        assert plan.requires_human_approval is True
        assert plan.template_version
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_deleted_test_degrades_to_manual_review_without_crashing() -> None:
    """Deleting a security test nulls the execution's test reference.

    A plan requested for such a finding must still answer honestly rather
    than fail with a stack trace.
    """

    session = _session()
    owner, project, finding = _seed_finding(session, config={"category": "jailbreak"})
    execution_id = finding.execution_id

    try:
        execution = session.get(Execution, execution_id)
        assert execution is not None
        test = session.get(SecurityTest, execution.test_id) if execution.test_id else None
        if test is not None:
            session.delete(test)
            session.commit()

        plan = get_remediation_plan(session, project.id, finding.id, owner)

        assert plan.kind == "manual_review"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_stranger_is_denied() -> None:
    session = _session()
    owner, project, finding = _seed_finding(session, config={"category": "jailbreak"})
    stranger = _register_user(session)

    try:
        with pytest.raises(PermissionDeniedError):
            get_remediation_plan(session, project.id, finding.id, stranger)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_viewer_member_can_read_the_plan() -> None:
    """Reading a suggestion is a read; a VIEWER must not be locked out."""

    session = _session()
    owner, project, finding = _seed_finding(session, config={"category": "rag_attack"})
    viewer = _register_user(session)

    try:
        create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=viewer.id, role=UserRole.VIEWER),
            owner,
        )

        plan = get_remediation_plan(session, project.id, finding.id, viewer)

        assert plan.kind == "application"
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_finding_paired_with_the_wrong_project_is_not_found() -> None:
    """A valid finding id paired with another project id must not answer."""

    session = _session()
    owner, project_a, finding = _seed_finding(session, config={"category": "jailbreak"})
    project_b = _create_project(session, owner)

    try:
        with pytest.raises(ProjectNotFoundError):
            get_remediation_plan(session, project_b.id, finding.id, owner)
    finally:
        session.delete(project_b)
        session.delete(project_a)
        session.commit()
        session.close()


def test_missing_finding_is_not_found() -> None:
    session = _session()
    owner, project, _finding = _seed_finding(session, config={"category": "jailbreak"})

    try:
        with pytest.raises(AssessmentNotFoundError):
            get_remediation_plan(session, project.id, uuid4(), owner)
    finally:
        session.delete(project)
        session.commit()
        session.close()

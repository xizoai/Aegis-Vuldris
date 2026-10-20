"""Candidate patch generation service tests.

These tests pin the honesty invariants of AutoFix's drafting stage: template
mode writes no diff and calls no model; a drafting model receives only the
finding summary and the explicitly supplied file; a proposal never changes a
finding's fix state; and stored credentials never appear in a proposal or in
the drafting request.
"""

import asyncio
import json
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from app.adapters.base import BaseTargetAdapter
from app.api.errors import (
    AssessmentNotFoundError,
    PatchDraftError,
    PermissionDeniedError,
    ProjectNotFoundError,
)
from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.finding import Finding, FindingStatus
from app.models.model import ModelRequest, ModelResponse
from app.models.patch_proposal import PatchApproach, PatchProposal, PatchProposalMode
from app.models.project import Project
from app.models.target import Target, TargetProvider, TargetStatus
from app.models.test import SecurityTest
from app.models.user import User, UserRole
from app.schemas import (
    CredentialCreate,
    ExecutionCreate,
    FindingCreate,
    FindingUpdate,
    PatchProposalCreate,
    ProjectCreate,
    ProjectMembershipCreate,
    SecurityTestCreate,
    TargetCreate,
    UserCreate,
)
from app.security.secrets import SecretStore
from app.services.assessments import (
    create_execution,
    create_finding,
    create_security_test,
    update_finding,
)
from app.services.auth import register_user
from app.services.credentials import create_target_credential
from app.services.memberships import create_project_membership
from app.services.patch_generation import (
    create_patch_proposal,
    list_patch_proposals,
    parse_draft_response,
)
from app.services.projects import create_project
from app.services.targets import create_target
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

ATTACK = {
    "id": "builtin/prompt-injection/01-direct-instruction-override",
    "version": "2.0.0",
}

FILE_PATH = "app/handlers.py"
FILE_CONTENT = "def handle(user_input: str) -> str:\n    return SYSTEM_PROMPT + user_input\n"

DIFF = (
    "--- a/app/handlers.py\n"
    "+++ b/app/handlers.py\n"
    "@@ -1,2 +1,3 @@\n"
    "+from app.security import build_safe_prompt\n"
    " def handle(user_input: str) -> str:\n"
    "-    return SYSTEM_PROMPT + user_input\n"
    "+    return build_safe_prompt(SYSTEM_PROMPT, user_input)\n"
)


class FakeDraftAdapter(BaseTargetAdapter):
    """A drafting adapter that returns a canned response without any network."""

    def __init__(self, output: str) -> None:
        super().__init__()
        self.output = output
        self.requests: list[ModelRequest] = []
        self.closed = False

    async def generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None = None,
    ) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(output=self.output)

    async def _generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None,
    ) -> ModelResponse:
        raise NotImplementedError("generate is overridden for tests")

    async def close(self) -> None:
        self.closed = True
        await super().close()


def _exploding_factory(*args: object, **kwargs: object) -> BaseTargetAdapter:
    """A factory that fails the test if template mode reaches the adapter layer."""

    raise AssertionError("template mode must not create a drafting adapter")


def _session() -> Session:
    return create_session_factory()()


def _register_user(session: Session, role: UserRole = UserRole.USER) -> User:
    user = register_user(
        session,
        UserCreate(
            email=f"patches-{uuid4()}@example.com",
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
        ProjectCreate(name=f"Patch Project {uuid4()}"),
        owner_id=owner.id,
    )


def _create_target(
    session: Session,
    project_id: UUID,
    owner: User,
    provider: TargetProvider = TargetProvider.OPENAI_COMPATIBLE,
) -> Target:
    payload = TargetCreate(
        project_id=project_id,
        name=f"Target {uuid4()}",
        provider=provider,
        endpoint="https://model.example.com/v1",
        model="drafting-model" if provider != TargetProvider.CUSTOM_REST else None,
        capabilities=["chat"],
        timeout_seconds=30.0,
        authorization_attestation=True,
    )
    return create_target(session, payload, project_id, owner)


def _seed_finding(
    session: Session,
    *,
    status: FindingStatus | None = None,
) -> tuple[User, Project, Target, SecurityTest, Finding]:
    """Create a project, target, test, execution, and finding.

    Returns ``(owner, project, target, test, finding)``.
    """

    owner = _register_user(session)
    project = _create_project(session, owner)
    target = _create_target(session, project.id, owner)
    test = create_security_test(
        session,
        project.id,
        SecurityTestCreate(
            name=f"Patch case {uuid4()}",
            provider="openai_compatible",
            config={"category": "prompt_injection", "attack": dict(ATTACK)},
        ),
        owner,
    )
    execution = create_execution(
        session,
        project.id,
        ExecutionCreate(test_id=test.id, target_id=target.id),
        owner,
    )
    finding = create_finding(
        session,
        FindingCreate(execution_id=execution.id, title="Instruction override"),
        owner,
    )
    if status is not None:
        finding = update_finding(session, finding.id, FindingUpdate(status=status), owner)
    return owner, project, target, test, finding


def _audit(session: Session, action: str, finding_id: UUID) -> AuditLog | None:
    return session.scalar(
        select(AuditLog).where(
            AuditLog.action == action,
            AuditLog.resource_id == str(finding_id),
        )
    )


def _factory(draft_adapter: FakeDraftAdapter) -> Callable[..., BaseTargetAdapter]:
    def build(*args: object, **kwargs: object) -> BaseTargetAdapter:
        return draft_adapter

    return build


def test_template_mode_records_intent_without_a_model_call() -> None:
    """No drafting target means no network and no diff -- by design."""

    session = _session()
    owner, project, _target, _test, finding = _seed_finding(session)

    try:
        proposal = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                PatchProposalCreate(),
                owner,
                adapter_factory=_exploding_factory,
            )
        )

        assert proposal.mode == PatchProposalMode.TEMPLATE
        assert proposal.diff_text is None
        assert proposal.files_touched == []
        assert proposal.approach == PatchApproach.PROMPT_ENGINEERING
        assert proposal.template_version == "1.0.0"
        assert proposal.prompt_hash is None

        audit = _audit(session, "patch.proposed", finding.id)
        assert audit is not None, "proposal creation was not audited"
        assert audit.event_metadata is not None
        assert audit.event_metadata["mode"] == "template"
        assert audit.event_metadata["proposal_id"] == str(proposal.id)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_template_mode_never_changes_finding_state() -> None:
    """A proposal is a draft; the fix state stays exactly where a human left it."""

    session = _session()
    owner, project, _target, _test, finding = _seed_finding(session, status=FindingStatus.FIXED)

    try:
        asyncio.run(
            create_patch_proposal(session, project.id, finding.id, PatchProposalCreate(), owner)
        )

        session.refresh(finding)
        assert finding.status == FindingStatus.FIXED
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_model_mode_stores_a_candidate_diff() -> None:
    """The drafting model's unified diff is stored for review, nothing more."""

    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)
    adapter = FakeDraftAdapter(DIFF)

    try:
        proposal = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                PatchProposalCreate(
                    file_path=FILE_PATH,
                    file_content=FILE_CONTENT,
                    drafting_target_id=target.id,
                ),
                owner,
                adapter_factory=_factory(adapter),
            )
        )

        assert proposal.mode == PatchProposalMode.LLM
        assert proposal.diff_text == DIFF.rstrip("\n")
        assert proposal.files_touched == [FILE_PATH]
        assert proposal.prompt_hash is not None and len(proposal.prompt_hash) == 64
        assert proposal.drafting_target_id == target.id
        assert proposal.drafting_model == "drafting-model"
        assert proposal.template_version is None

        assert len(adapter.requests) == 1
        assert adapter.closed, "the drafting adapter must be closed"

        session.refresh(finding)
        assert finding.status == FindingStatus.OPEN
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_model_mode_audit_records_provenance() -> None:
    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)
    adapter = FakeDraftAdapter(DIFF)

    try:
        proposal = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                PatchProposalCreate(
                    file_path=FILE_PATH,
                    file_content=FILE_CONTENT,
                    drafting_target_id=target.id,
                ),
                owner,
                adapter_factory=_factory(adapter),
            )
        )

        audit = _audit(session, "patch.proposed", finding.id)
        assert audit is not None
        assert audit.event_metadata is not None
        assert audit.event_metadata["mode"] == "llm"
        assert audit.event_metadata["drafting_target_id"] == str(target.id)
        assert audit.event_metadata["drafting_model"] == "drafting-model"
        assert audit.event_metadata["prompt_hash"] == proposal.prompt_hash
        assert audit.event_metadata["files_touched"] == [FILE_PATH]
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_prompt_hash_is_stable_for_identical_inputs() -> None:
    """Same finding, same file, same prompt: the recorded hash must match."""

    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)
    payload = PatchProposalCreate(
        file_path=FILE_PATH,
        file_content=FILE_CONTENT,
        drafting_target_id=target.id,
    )

    try:
        first = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                payload,
                owner,
                adapter_factory=_factory(FakeDraftAdapter(DIFF)),
            )
        )
        second = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                payload,
                owner,
                adapter_factory=_factory(FakeDraftAdapter(DIFF)),
            )
        )
        third = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                PatchProposalCreate(
                    file_path=FILE_PATH,
                    file_content=FILE_CONTENT + "# comment\n",
                    drafting_target_id=target.id,
                ),
                owner,
                adapter_factory=_factory(FakeDraftAdapter(DIFF)),
            )
        )

        assert first.prompt_hash == second.prompt_hash
        assert first.prompt_hash != third.prompt_hash
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_model_refusal_records_no_diff() -> None:
    """The NO_DIFF sentinel is an honest refusal, not an error to hide."""

    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)

    try:
        proposal = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                PatchProposalCreate(
                    file_path=FILE_PATH,
                    file_content=FILE_CONTENT,
                    drafting_target_id=target.id,
                ),
                owner,
                adapter_factory=_factory(FakeDraftAdapter("NO_DIFF")),
            )
        )

        assert proposal.mode == PatchProposalMode.LLM
        assert proposal.diff_text is None
        assert proposal.files_touched == []
        assert "could not produce" in proposal.rationale
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_non_diff_response_is_rejected_and_stores_nothing() -> None:
    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)

    try:
        with pytest.raises(PatchDraftError):
            asyncio.run(
                create_patch_proposal(
                    session,
                    project.id,
                    finding.id,
                    PatchProposalCreate(
                        file_path=FILE_PATH,
                        file_content=FILE_CONTENT,
                        drafting_target_id=target.id,
                    ),
                    owner,
                    adapter_factory=_factory(
                        FakeDraftAdapter("Sure! Here is how I would fix it: ...")
                    ),
                )
            )

        assert (
            session.scalars(
                select(PatchProposal).where(PatchProposal.finding_id == finding.id)
            ).all()
            == []
        )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_suspicious_diff_paths_are_rejected() -> None:
    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)
    bad_diff = "--- a/x\n+++ b/../etc/passwd\n@@ -1 +1 @@\n-a\n+b\n"

    try:
        with pytest.raises(PatchDraftError):
            asyncio.run(
                create_patch_proposal(
                    session,
                    project.id,
                    finding.id,
                    PatchProposalCreate(
                        file_path=FILE_PATH,
                        file_content=FILE_CONTENT,
                        drafting_target_id=target.id,
                    ),
                    owner,
                    adapter_factory=_factory(FakeDraftAdapter(bad_diff)),
                )
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_parse_accepts_a_fenced_diff() -> None:
    fenced = "```diff\n" + DIFF + "```\n"

    diff_text, files = parse_draft_response(fenced)

    assert diff_text == DIFF.rstrip("\n")
    assert files == [FILE_PATH]


def test_custom_rest_target_cannot_draft() -> None:
    session = _session()
    owner, project, _target, _test, finding = _seed_finding(session)
    custom = _create_target(session, project.id, owner, provider=TargetProvider.CUSTOM_REST)

    try:
        with pytest.raises(PatchDraftError):
            asyncio.run(
                create_patch_proposal(
                    session,
                    project.id,
                    finding.id,
                    PatchProposalCreate(
                        file_path=FILE_PATH,
                        file_content=FILE_CONTENT,
                        drafting_target_id=custom.id,
                    ),
                    owner,
                )
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_drafting_target_must_be_in_the_project() -> None:
    session = _session()
    owner, project, _target, _test, finding = _seed_finding(session)
    other_project = _create_project(session, owner)
    foreign = _create_target(session, other_project.id, owner)

    try:
        with pytest.raises(AssessmentNotFoundError):
            asyncio.run(
                create_patch_proposal(
                    session,
                    project.id,
                    finding.id,
                    PatchProposalCreate(
                        file_path=FILE_PATH,
                        file_content=FILE_CONTENT,
                        drafting_target_id=foreign.id,
                    ),
                    owner,
                )
            )
    finally:
        session.delete(other_project)
        session.delete(project)
        session.commit()
        session.close()


def test_inactive_drafting_target_is_rejected() -> None:
    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)
    target.status = TargetStatus.INACTIVE
    session.commit()

    try:
        with pytest.raises(PatchDraftError):
            asyncio.run(
                create_patch_proposal(
                    session,
                    project.id,
                    finding.id,
                    PatchProposalCreate(
                        file_path=FILE_PATH,
                        file_content=FILE_CONTENT,
                        drafting_target_id=target.id,
                    ),
                    owner,
                )
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_viewer_cannot_draft_but_can_list() -> None:
    """Drafting spends model calls, so it is a write; reading stays allowed."""

    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)
    viewer = _register_user(session)

    try:
        create_project_membership(
            session,
            project.id,
            ProjectMembershipCreate(user_id=viewer.id, role=UserRole.VIEWER),
            owner,
        )

        with pytest.raises(PermissionDeniedError):
            asyncio.run(
                create_patch_proposal(
                    session,
                    project.id,
                    finding.id,
                    PatchProposalCreate(
                        file_path=FILE_PATH,
                        file_content=FILE_CONTENT,
                        drafting_target_id=target.id,
                    ),
                    viewer,
                )
            )

        assert list_patch_proposals(session, project.id, finding.id, viewer) == []
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_stranger_is_denied() -> None:
    session = _session()
    _owner, project, _target, _test, finding = _seed_finding(session)
    stranger = _register_user(session)

    try:
        with pytest.raises(PermissionDeniedError):
            asyncio.run(
                create_patch_proposal(
                    session, project.id, finding.id, PatchProposalCreate(), stranger
                )
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_finding_paired_with_the_wrong_project_is_not_found() -> None:
    session = _session()
    owner, project_a, _target, _test, finding = _seed_finding(session)
    project_b = _create_project(session, owner)

    try:
        with pytest.raises(ProjectNotFoundError):
            asyncio.run(
                create_patch_proposal(
                    session, project_b.id, finding.id, PatchProposalCreate(), owner
                )
            )
    finally:
        session.delete(project_b)
        session.delete(project_a)
        session.commit()
        session.close()


def test_missing_finding_is_not_found() -> None:
    session = _session()
    owner, project, _target, _test, _finding = _seed_finding(session)

    try:
        with pytest.raises(AssessmentNotFoundError):
            asyncio.run(
                create_patch_proposal(session, project.id, uuid4(), PatchProposalCreate(), owner)
            )
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_listing_returns_proposals_oldest_first_across_modes() -> None:
    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)

    try:
        first = asyncio.run(
            create_patch_proposal(session, project.id, finding.id, PatchProposalCreate(), owner)
        )
        second = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                PatchProposalCreate(
                    file_path=FILE_PATH,
                    file_content=FILE_CONTENT,
                    drafting_target_id=target.id,
                ),
                owner,
                adapter_factory=_factory(FakeDraftAdapter(DIFF)),
            )
        )

        proposals = list_patch_proposals(session, project.id, finding.id, owner)

        assert [proposal.id for proposal in proposals] == [first.id, second.id]
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_credentials_never_reach_a_proposal_or_the_drafting_prompt() -> None:
    """Stored credentials are not part of the request or the stored row."""

    session = _session()
    owner, project, target, _test, finding = _seed_finding(session)
    store = SecretStore("unit-test-secret-key")
    secret_value = "sk-live-supersecret-123"
    create_target_credential(
        session,
        store,
        target.id,
        CredentialCreate(credential_type="api_key", value=secret_value),
        owner,
    )
    adapter = FakeDraftAdapter(DIFF)

    try:
        proposal = asyncio.run(
            create_patch_proposal(
                session,
                project.id,
                finding.id,
                PatchProposalCreate(
                    file_path=FILE_PATH,
                    file_content=FILE_CONTENT,
                    drafting_target_id=target.id,
                ),
                owner,
                adapter_factory=_factory(adapter),
                store=store,
            )
        )

        stored = json.dumps(
            {
                "rationale": proposal.rationale,
                "diff_text": proposal.diff_text,
                "files_touched": list(proposal.files_touched),
                "prompt_hash": proposal.prompt_hash,
                "drafting_model": proposal.drafting_model,
            }
        )
        assert secret_value not in stored

        assert len(adapter.requests) == 1
        request_dump = json.dumps(
            [message.model_dump() for message in adapter.requests[0].messages]
        )
        assert secret_value not in request_dump
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_file_pair_must_be_supplied_together() -> None:
    with pytest.raises(ValidationError):
        PatchProposalCreate(file_path="app/handlers.py")


def test_drafting_requires_a_file_to_patch() -> None:
    with pytest.raises(ValidationError):
        PatchProposalCreate(drafting_target_id=uuid4())

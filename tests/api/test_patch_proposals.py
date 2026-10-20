"""Candidate patch route contract: statuses, authz, and audit.

Drafting is a write (it spends model calls) but never applies anything and
never changes a finding's state. Template mode makes no model call at all;
model mode is exercised through a stubbed adapter, so these tests cover the
API contract while the service tests cover the drafting invariants.
"""

from uuid import UUID, uuid4

from app.adapters.base import BaseTargetAdapter
from app.db.session import create_session_factory
from app.main import app
from app.models.audit_log import AuditLog
from app.models.finding import Finding, FindingStatus
from app.models.model import ModelRequest, ModelResponse
from app.models.project import Project
from app.models.target import Target, TargetProvider
from app.models.user import User, UserRole
from app.schemas import (
    ExecutionCreate,
    FindingCreate,
    ProjectMembershipCreate,
    SecurityTestCreate,
    TargetCreate,
)
from app.services.assessments import create_execution, create_finding, create_security_test
from app.services.memberships import create_project_membership
from app.services.targets import create_target
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"

DIFF = (
    "--- a/app/handlers.py\n"
    "+++ b/app/handlers.py\n"
    "@@ -1,2 +1,3 @@\n"
    "+from app.security import build_safe_prompt\n"
    " def handle(user_input: str) -> str:\n"
    "-    return SYSTEM_PROMPT + user_input\n"
    "+    return build_safe_prompt(SYSTEM_PROMPT, user_input)\n"
)

FILE_PATH = "app/handlers.py"
FILE_CONTENT = "def handle(user_input: str) -> str:\n    return SYSTEM_PROMPT + user_input\n"


class FakeDraftAdapter(BaseTargetAdapter):
    """A drafting adapter that returns a canned response without any network."""

    def __init__(self, output: str) -> None:
        super().__init__()
        self.output = output

    async def generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None = None,
    ) -> ModelResponse:
        return ModelResponse(output=self.output)

    async def _generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None,
    ) -> ModelResponse:
        raise NotImplementedError("generate is overridden for tests")


def _register(email: str) -> tuple[str, dict[str, str]]:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return email, {"Authorization": f"Bearer {token}"}


def _create_target(session, project_id: UUID, owner: User) -> Target:
    return create_target(
        session,
        TargetCreate(
            project_id=project_id,
            name=f"Target {uuid4()}",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="drafting-model",
            capabilities=["chat"],
            timeout_seconds=30.0,
            authorization_attestation=True,
        ),
        project_id,
        owner,
    )


def _seed() -> tuple[str, str, str, str, dict[str, str]]:
    """Create an owner, project, target, test, execution, and finding.

    Returns ``(project_id, finding_id, target_id, owner_email, owner_auth)``.
    """

    email, auth = _register(f"patches-owner-{uuid4()}@example.com")
    session = create_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        project_id = client.post(
            "/api/v1/projects", headers=auth, json={"name": f"Patches {uuid4()}"}
        ).json()["id"]

        target = _create_target(session, UUID(project_id), user)
        test = create_security_test(
            session,
            UUID(project_id),
            SecurityTestCreate(
                name=f"Case {uuid4()}",
                provider="openai_compatible",
                config={
                    "category": "prompt_injection",
                    "attack": {
                        "id": "builtin/prompt-injection/01-direct-instruction-override",
                        "version": "2.0.0",
                    },
                },
            ),
            user,
        )
        execution = create_execution(
            session,
            UUID(project_id),
            ExecutionCreate(test_id=test.id, target_id=target.id),
            user,
        )
        finding = create_finding(
            session,
            FindingCreate(execution_id=execution.id, title="Instruction override"),
            user,
        )
        return project_id, str(finding.id), str(target.id), email, auth
    finally:
        session.close()


def _cleanup(project_id: str, *emails: str) -> None:
    session = create_session_factory()()
    try:
        project = session.get(Project, UUID(project_id))
        if project is not None:
            session.delete(project)
        for email in emails:
            user = session.scalar(select(User).where(User.email == email))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()


def _patches_url(project_id: str, finding_id: str) -> str:
    return f"/api/v1/projects/{project_id}/assessments/findings/{finding_id}/patches"


def test_create_template_proposal() -> None:
    project_id, finding_id, _target_id, owner_email, auth = _seed()

    try:
        response = client.post(_patches_url(project_id, finding_id), headers=auth, json={})

        assert response.status_code == 201
        body = response.json()
        assert body["mode"] == "template"
        assert body["diff_text"] is None
        assert body["files_touched"] == []
        assert body["approach"] == "prompt_engineering"
        assert body["template_version"] == "1.0.0"

        session = create_session_factory()()
        try:
            finding = session.get(Finding, UUID(finding_id))
            assert finding is not None
            assert finding.status == FindingStatus.OPEN
            audit = session.scalar(
                select(AuditLog).where(
                    AuditLog.action == "patch.proposed",
                    AuditLog.resource_id == finding_id,
                )
            )
            assert audit is not None
            assert audit.event_metadata is not None
            assert audit.event_metadata["mode"] == "template"
        finally:
            session.close()
    finally:
        _cleanup(project_id, owner_email)


def test_list_returns_created_proposals_in_order() -> None:
    project_id, finding_id, _target_id, owner_email, auth = _seed()

    try:
        first = client.post(_patches_url(project_id, finding_id), headers=auth, json={}).json()
        second = client.post(_patches_url(project_id, finding_id), headers=auth, json={}).json()

        listed = client.get(_patches_url(project_id, finding_id), headers=auth)

        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [first["id"], second["id"]]
    finally:
        _cleanup(project_id, owner_email)


def test_patch_routes_require_authentication() -> None:
    project_id, finding_id, _target_id, owner_email, _auth = _seed()

    try:
        assert client.post(_patches_url(project_id, finding_id), json={}).status_code == 401
        assert client.get(_patches_url(project_id, finding_id)).status_code == 401
    finally:
        _cleanup(project_id, owner_email)


def test_drafting_without_a_file_is_rejected() -> None:
    project_id, finding_id, target_id, owner_email, auth = _seed()

    try:
        response = client.post(
            _patches_url(project_id, finding_id),
            headers=auth,
            json={"drafting_target_id": target_id},
        )

        assert response.status_code == 422
    finally:
        _cleanup(project_id, owner_email)


def test_file_path_and_content_must_come_together() -> None:
    project_id, finding_id, _target_id, owner_email, auth = _seed()

    try:
        response = client.post(
            _patches_url(project_id, finding_id),
            headers=auth,
            json={"file_path": FILE_PATH},
        )

        assert response.status_code == 422
    finally:
        _cleanup(project_id, owner_email)


def test_model_draft_is_stored_with_provenance(monkeypatch) -> None:
    project_id, finding_id, target_id, owner_email, auth = _seed()
    monkeypatch.setattr(
        "app.services.patch_generation.create_model_adapter",
        lambda provider, credential_resolver=None: FakeDraftAdapter(DIFF),
    )

    try:
        response = client.post(
            _patches_url(project_id, finding_id),
            headers=auth,
            json={
                "file_path": FILE_PATH,
                "file_content": FILE_CONTENT,
                "drafting_target_id": target_id,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["mode"] == "llm"
        assert body["diff_text"] == DIFF.rstrip("\n")
        assert body["files_touched"] == [FILE_PATH]
        assert body["prompt_hash"] is not None and len(body["prompt_hash"]) == 64
        assert body["drafting_target_id"] == target_id
        assert body["drafting_model"] == "drafting-model"

        session = create_session_factory()()
        try:
            finding = session.get(Finding, UUID(finding_id))
            assert finding is not None
            assert finding.status == FindingStatus.OPEN
        finally:
            session.close()
    finally:
        _cleanup(project_id, owner_email)


def test_invalid_model_output_is_a_422_with_code(monkeypatch) -> None:
    project_id, finding_id, target_id, owner_email, auth = _seed()
    monkeypatch.setattr(
        "app.services.patch_generation.create_model_adapter",
        lambda provider, credential_resolver=None: FakeDraftAdapter("not a diff at all"),
    )

    try:
        response = client.post(
            _patches_url(project_id, finding_id),
            headers=auth,
            json={
                "file_path": FILE_PATH,
                "file_content": FILE_CONTENT,
                "drafting_target_id": target_id,
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "PATCH_DRAFT_FAILED"
    finally:
        _cleanup(project_id, owner_email)


def test_viewer_can_list_but_not_draft() -> None:
    project_id, finding_id, _target_id, owner_email, _auth = _seed()
    viewer_email, viewer_auth = _register(f"patches-viewer-{uuid4()}@example.com")

    session = create_session_factory()()
    try:
        owner = session.scalar(select(User).where(User.email == owner_email))
        viewer = session.scalar(select(User).where(User.email == viewer_email))
        assert owner is not None and viewer is not None
        create_project_membership(
            session,
            UUID(project_id),
            ProjectMembershipCreate(user_id=viewer.id, role=UserRole.VIEWER),
            owner,
        )
    finally:
        session.close()

    try:
        denied = client.post(_patches_url(project_id, finding_id), headers=viewer_auth, json={})
        assert denied.status_code == 403

        listed = client.get(_patches_url(project_id, finding_id), headers=viewer_auth)
        assert listed.status_code == 200
        assert listed.json() == []
    finally:
        _cleanup(project_id, owner_email, viewer_email)


def test_stranger_is_denied() -> None:
    project_id, finding_id, _target_id, owner_email, _auth = _seed()
    stranger_email, stranger_auth = _register(f"patches-stranger-{uuid4()}@example.com")

    try:
        denied = client.post(_patches_url(project_id, finding_id), headers=stranger_auth, json={})
        assert denied.status_code == 403
    finally:
        _cleanup(project_id, owner_email, stranger_email)


def test_finding_from_another_project_is_not_found() -> None:
    """The same owner asking under the wrong project gets a 404, not a proposal."""

    project_id, finding_id, _target_id, owner_email, auth = _seed()
    other_project_id = client.post(
        "/api/v1/projects", headers=auth, json={"name": f"Other {uuid4()}"}
    ).json()["id"]

    try:
        response = client.post(_patches_url(other_project_id, finding_id), headers=auth, json={})

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    finally:
        session = create_session_factory()()
        try:
            other = session.get(Project, UUID(other_project_id))
            if other is not None:
                session.delete(other)
            session.commit()
        finally:
            session.close()
        _cleanup(project_id, owner_email)

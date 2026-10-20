"""Aegis LLM shim API tests: the claim-to-completion round trip.

These exercise the full HTTP surface with a mocked adapter, which is what the
garak and PyRIT integration will present as in phase 2: an OpenAI-shaped
request in, an OpenAI-shaped completion out, with every other input rejected.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from app.adapters.errors import ModelProviderError
from app.db.session import create_session_factory
from app.main import app
from app.models.external_scan import ExternalScan, ExternalScanStatus
from app.models.model import ModelResponse
from app.models.target import TargetProvider
from fastapi.testclient import TestClient

client = TestClient(app)

PASSWORD = "a-very-strong-password-123"
RUNNER_TOKEN = "test-runner-token"

_SHIM_PATH = "/api/v1/external/llm/{scan_id}/v1/chat/completions"

# Filled by the helpers, drained by the autouse fixture. Deleting the project
# cascades to its targets and scans, so a failed test cannot leave a queued
# scan behind that steals a later test's claim.
_CREATED_PROJECTS: list[str] = []
_CREATED_EMAILS: list[str] = []


@pytest.fixture(autouse=True)
def _shim_isolation(monkeypatch) -> Iterator[None]:
    """Refuse to start with foreign queue work; always drain our own."""

    from app.models.project import Project
    from sqlalchemy import select

    session = create_session_factory()()
    try:
        leftover = session.scalar(
            select(ExternalScan).where(
                ExternalScan.status.in_([ExternalScanStatus.QUEUED, ExternalScanStatus.RUNNING])
            )
        )
        if leftover is not None:
            pytest.skip("queue already contains work from another test")
    finally:
        session.close()

    yield

    session = create_session_factory()()
    try:
        for project_id in _CREATED_PROJECTS:
            project = session.get(Project, UUID(project_id))
            if project is not None:
                session.delete(project)
        for email in _CREATED_EMAILS:
            from app.models.user import User

            user = session.scalar(select(User).where(User.email == email.lower()))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()
        _CREATED_PROJECTS.clear()
        _CREATED_EMAILS.clear()


class SimpleNamespaceSetting:
    def __init__(self, runner_token: str, lease: int) -> None:
        self.runner_service_token = runner_token
        self.runner_claim_lease_seconds = lease


class _EchoAdapter:
    """Stands in for a model adapter, recording what the shim forwarded."""

    last_target_id = None
    last_request = None

    def __init__(self, capture: dict, output: str = "mocked completion") -> None:
        self._capture = capture
        self._output = output

    async def generate(self, target, request, **_kwargs) -> ModelResponse:
        self._capture["target_id"] = target.id
        self._capture["provider"] = target.provider
        self._capture["request"] = request
        return ModelResponse(
            output=self._output,
            finish_reason="stop",
            model=target.model,
            usage=None,
        )

    async def close(self) -> None:
        self._capture["closed"] = True


@pytest.fixture
def runner_settings(monkeypatch):
    settings = SimpleNamespaceSetting(RUNNER_TOKEN, 60)
    monkeypatch.setattr("app.security.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.internal_scans.get_settings", lambda: settings)
    return settings


@pytest.fixture
def _reset_shim_rate_limit():
    from app.api.routes import external_llm

    external_llm._shim_rate_limiter.reset()
    yield
    external_llm._shim_rate_limiter.reset()


def _register_and_login(email: str) -> str:
    _CREATED_EMAILS.append(email)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _project_and_target(token: str) -> tuple[str, str]:
    project = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"name": f"Shim API Project {uuid4()}"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    _CREATED_PROJECTS.append(project_id)

    target = client.post(
        "/api/v1/targets",
        headers=_auth(token),
        json={
            "project_id": project_id,
            "name": f"Shim API Target {uuid4()}",
            "provider": TargetProvider.OPENAI_COMPATIBLE.value,
            "endpoint": "https://mock-target.example/v1",
            "model": "mock-model",
            "capabilities": ["chat"],
            "authorization_attestation": True,
        },
    )
    assert target.status_code == 201, target.text
    return project_id, target.json()["id"]


def _queue_scan(token: str, project_id: str, target_id: str) -> str:
    scan = client.post(
        f"/api/v1/projects/{project_id}/scans",
        headers=_auth(token),
        json={"target_id": target_id, "tool": "garak", "config": {}},
    )
    assert scan.status_code == 202, scan.text
    return scan.json()["id"]


def _claim(email: str) -> tuple[str, str]:
    """Queue and claim a scan; return (scan_id, llm_token)."""

    token = _register_and_login(email)
    project_id, target_id = _project_and_target(token)
    scan_id = _queue_scan(token, project_id, target_id)

    claim = client.post(
        "/api/v1/internal/scans/claim",
        headers=_auth(RUNNER_TOKEN),
    )
    assert claim.status_code == 200, claim.text
    response = claim.json()
    assert response["scan"] is not None, "claim race: another test's scan won"
    assert response["scan"]["id"] == scan_id
    assert response["llm_token"], "claim must mint a scan token"

    return scan_id, response["llm_token"]


def test_shim_round_trips_an_openai_request(
    runner_settings, _reset_shim_rate_limit, monkeypatch
) -> None:
    capture: dict = {}
    monkeypatch.setattr(
        "app.api.routes.external_llm.create_model_adapter",
        lambda provider, credential_resolver=None: _EchoAdapter(capture),
    )

    email = f"shim-ok-{uuid4()}@example.com"
    scan_id, llm_token = _claim(email)

    response = client.post(
        _SHIM_PATH.format(scan_id=scan_id),
        headers=_auth(llm_token),
        json={
            "model": "ignored",
            "messages": [{"role": "user", "content": "say hi"}],
            "temperature": 1.5,
            "max_tokens": 128,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "mock-model"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "mocked completion"

    # The call went to the scan's bound target, not to anything the body named.
    session = create_session_factory()()
    try:
        stored = session.get(ExternalScan, scan_id)
        assert stored is not None
        assert str(capture["target_id"]) == str(stored.target_id)
        assert capture["provider"].value == "openai_compatible"
        assert capture["closed"] is True
        assert capture["request"].messages[0].content == "say hi"
        # Dropping the caller's model name is the point: it may not choose a
        # deployment on the bound endpoint.
        assert capture["request"] is not None

        assert stored.forwarded_requests == 1
    finally:
        session.close()


def test_shim_rejects_another_scans_token(runner_settings, _reset_shim_rate_limit) -> None:
    email_a = f"shim-a-{uuid4()}@example.com"
    email_b = f"shim-b-{uuid4()}@example.com"
    scan_a, token_a = _claim(email_a)
    scan_b, _token_b = _claim(email_b)

    response = client.post(
        _SHIM_PATH.format(scan_id=scan_b),
        headers=_auth(token_a),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SCAN_TOKEN_INVALID"


def test_shim_rejects_missing_and_garbage_tokens(runner_settings, _reset_shim_rate_limit) -> None:
    email = f"shim-noauth-{uuid4()}@example.com"
    scan_id, _ = _claim(email)
    path = _SHIM_PATH.format(scan_id=scan_id)

    missing = client.post(path, json={"messages": [{"role": "user", "content": "hi"}]})
    assert missing.status_code == 401

    garbage = client.post(
        path,
        headers=_auth("not-a-jwt"),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert garbage.status_code == 401

    user_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    user_token = user_login.json()["access_token"]
    as_user = client.post(
        path, headers=_auth(user_token), json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert as_user.status_code == 401


def test_shim_rejects_a_url_or_target_in_the_body(runner_settings, _reset_shim_rate_limit) -> None:
    """Extra-forbid rejects anything that could name a destination."""

    email = f"shim-ssrf-{uuid4()}@example.com"
    scan_id, llm_token = _claim(email)

    for smuggle in (
        {"messages": [{"role": "user", "content": "hi"}], "url": "http://169.254.169.254/latest"},
        {"messages": [{"role": "user", "content": "hi"}], "host": "internal.svc"},
        {
            "messages": [{"role": "user", "content": "hi"}],
            "target_id": str(uuid4()),
        },
    ):
        response = client.post(
            _SHIM_PATH.format(scan_id=scan_id),
            headers=_auth(llm_token),
            json=smuggle,
        )
        assert response.status_code == 422, smuggle


def test_shim_rejects_empty_and_malformed_messages(runner_settings, _reset_shim_rate_limit) -> None:
    email = f"shim-malformed-{uuid4()}@example.com"
    scan_id, llm_token = _claim(email)
    path = _SHIM_PATH.format(scan_id=scan_id)
    headers = _auth(llm_token)

    assert client.post(path, headers=headers, json={"messages": []}).status_code == 422
    assert (
        client.post(path, headers=headers, json={"messages": [{"role": "user"}]}).status_code == 422
    )
    assert (
        client.post(
            path, headers=headers, json={"messages": [{"role": "user", "content": ""}]}
        ).status_code
        == 422
    )


def test_shim_rejects_streaming(runner_settings, _reset_shim_rate_limit) -> None:
    email = f"shim-stream-{uuid4()}@example.com"
    scan_id, llm_token = _claim(email)

    response = client.post(
        _SHIM_PATH.format(scan_id=scan_id),
        headers=_auth(llm_token),
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )

    # A streamed response cannot be rebuilt into the OpenAI shape the runner
    # expects, so it is refused rather than silently flatted.
    assert response.status_code == 422


def test_shim_surfaces_upstream_model_errors(
    runner_settings, _reset_shim_rate_limit, monkeypatch
) -> None:
    class _FailingAdapter:
        async def generate(self, target, request, **_kwargs):
            raise ModelProviderError("model provider returned HTTP 429")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        "app.api.routes.external_llm.create_model_adapter",
        lambda provider, credential_resolver=None: _FailingAdapter(),
    )

    email = f"shim-fail-{uuid4()}@example.com"
    scan_id, llm_token = _claim(email)

    response = client.post(
        _SHIM_PATH.format(scan_id=scan_id),
        headers=_auth(llm_token),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "TARGET_UPSTREAM_ERROR"

    # A failed forward is not a forwarded request.
    session = create_session_factory()()
    try:
        stored = session.get(ExternalScan, scan_id)
        assert stored is not None
        assert stored.forwarded_requests == 0
    finally:
        session.close()


def test_shim_rejects_a_completed_scans_token(runner_settings, _reset_shim_rate_limit) -> None:
    email = f"shim-done-{uuid4()}@example.com"
    scan_id, llm_token = _claim(email)

    complete = client.post(
        f"/api/v1/internal/scans/{scan_id}/complete",
        headers=_auth(RUNNER_TOKEN),
        json={"status": "completed"},
    )
    assert complete.status_code == 200

    response = client.post(
        _SHIM_PATH.format(scan_id=scan_id),
        headers=_auth(llm_token),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 401

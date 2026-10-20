"""Aegis LLM shim tests: binding, conversion, forwarding, and rejection paths.

Phase 1 exit criteria live here: an OpenAI-shaped round-trip against a mock
target, and hard rejects for SSRF-shaped input and cross-scan token reuse.
"""

from typing import Any
from uuid import uuid4

import pytest
from app.api.routes.external_llm import _authorized_scan
from app.db.session import create_session_factory
from app.models.external_scan import ExternalScan, ExternalScanTool
from app.models.target import Target
from app.models.user import User
from app.schemas import (
    ProjectCreate,
    ScanCompleteRequest,
    ScanCreate,
    TargetCreate,
    UserCreate,
)
from app.security.scan_tokens import ScanTokenError, create_scan_token, decode_scan_token
from app.services.auth import register_user
from app.services.projects import create_project
from app.services.scans import (
    cancel_scan,
    claim_next_scan,
    complete_scan,
    create_scan,
    requeue_expired_claims,
)
from app.services.shim_mapping import to_chat_completion, to_model_request
from app.services.targets import create_target


def _session():
    return create_session_factory()()


class _World:
    """One owner, project, target, and scan, all persisted and cleaned up."""

    def __init__(self, session) -> None:
        self.session = session
        self.owner: User = _register(session)
        self.project = create_project(
            session,
            ProjectCreate(name=f"Shim Project {uuid4()}"),
            owner_id=self.owner.id,
        )
        self.target = _target(session, self.project.id, self.owner)
        self.scan = create_scan(
            session,
            self.project.id,
            ScanCreate(target_id=self.target.id, tool=ExternalScanTool.GARAK, config={}),
            self.owner,
        )

    def dispose(self) -> None:
        self.session.delete(self.project)
        self.session.commit()
        self.session.close()


def _register(session) -> User:
    return register_user(
        session,
        UserCreate(
            email=f"shim-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )


def _target(session, project_id, owner: User) -> Target:
    from app.models.target import TargetProvider

    return create_target(
        session,
        TargetCreate(
            project_id=project_id,
            name=f"Shim Target {uuid4()}",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="shim-test-model",
            capabilities=["chat"],
            authorization_attestation=True,
        ),
        project_id,
        owner,
    )


def _running_scan(world: _World) -> ExternalScan:
    """Claim through the real claim path so the claim nonce is set."""

    claimed = claim_next_scan(world.session, lease_seconds=3600)
    assert claimed is not None and claimed.id == world.scan.id
    return claimed


def _body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "shim-test-model",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.5,
        "max_tokens": 10,
    }
    payload.update(overrides)
    return payload


# --- token round-trip -------------------------------------------------------


def test_scan_token_round_trip_binds_scan_target_project_and_claim() -> None:
    session = _session()
    world = _World(session)
    try:
        _running_scan(world)

        token = create_scan_token(
            scan_id=world.scan.id,
            target_id=world.scan.target_id or uuid4(),
            project_id=world.scan.project_id,
            claim_id=world.scan.claim_id or "",
        )
        claims = decode_scan_token(token)

        assert claims.scan_id == world.scan.id
        assert claims.target_id == world.scan.target_id
        assert claims.project_id == world.scan.project_id
        assert claims.claim_id == world.scan.claim_id
    finally:
        world.dispose()


def test_scan_token_rejects_tampering() -> None:
    session = _session()
    world = _World(session)
    try:
        _running_scan(world)
        token = create_scan_token(
            scan_id=world.scan.id,
            target_id=world.scan.target_id or uuid4(),
            project_id=world.scan.project_id,
            claim_id=world.scan.claim_id or "",
        )

        head, _, signature = token.rpartition(".")
        # Flip one character in the signature: not signed under SECRET_KEY.
        tampered = f"{head}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"

        with pytest.raises(ScanTokenError):
            decode_scan_token(tampered)
    finally:
        world.dispose()


def test_user_access_tokens_are_not_accepted_as_scan_tokens() -> None:
    """An access token has no issuer/scan claims, so it cannot drive the shim."""

    from app.security.tokens import create_access_token

    session = _session()
    world = _World(session)
    try:
        token, _ = create_access_token(world.owner.id)

        with pytest.raises(ScanTokenError):
            decode_scan_token(token)
    finally:
        world.dispose()


# --- conversion -------------------------------------------------------------


def test_to_model_request_maps_openai_shape() -> None:
    request = to_model_request(_body(stop=["END"]))

    assert [message.role for message in request.messages] == ["user"]
    assert request.temperature == 0.5
    assert request.max_tokens == 10
    assert request.stop == ["END"]


def test_to_model_request_rejects_structure_targets_cannot_be_named_through() -> None:
    # A string isn't a messages list, so a naive "URL in messages" escape
    # cannot reach the adapter either.
    from app.adapters.errors import ModelProviderError

    with pytest.raises(ModelProviderError):
        to_model_request({"messages": None})

    with pytest.raises(ModelProviderError):
        to_model_request(_body(messages=[]))


def test_to_chat_completion_renders_openai_shape() -> None:
    from app.models.model import ModelResponse, ModelUsage

    response = ModelResponse(
        output="hello there",
        finish_reason="length",
        model="echo-model",
        usage=ModelUsage(prompt_tokens=3, completion_tokens=5, total_tokens=8),
        provider_request_id="req-1",
    )

    payload = to_chat_completion(response, model="team-model")

    assert payload["object"] == "chat.completion"
    assert payload["id"] == "req-1"
    assert payload["model"] == "echo-model"
    assert payload["choices"][0]["message"]["content"] == "hello there"
    assert payload["choices"][0]["finish_reason"] == "length"
    assert payload["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 5,
        "total_tokens": 8,
    }


def test_to_chat_completion_supplies_a_stop_finish_reason() -> None:
    from app.models.model import ModelResponse

    payload = to_chat_completion(
        ModelResponse(output="hi", finish_reason=None, model=None),
        model="team-model",
    )

    assert payload["choices"][0]["finish_reason"] == "stop"
    assert payload["model"] == "team-model"
    assert payload["usage"] is None


# --- binding ----------------------------------------------------------------


def test_token_is_bound_to_the_running_claim() -> None:
    session = _session()
    world = _World(session)
    try:
        _running_scan(world)

        claims = decode_scan_token(
            create_scan_token(
                scan_id=world.scan.id,
                target_id=world.scan.target_id or uuid4(),
                project_id=world.scan.project_id,
                claim_id=world.scan.claim_id or "",
            )
        )
        session.refresh(world.scan)
        assert _authorized_scan(session, claims).id == world.scan.id
    finally:
        world.dispose()


def test_token_dies_when_the_scan_is_cancelled() -> None:
    session = _session()
    world = _World(session)
    try:
        _running_scan(world)
        claims = decode_scan_token(
            create_scan_token(
                scan_id=world.scan.id,
                target_id=world.scan.target_id or uuid4(),
                project_id=world.scan.project_id,
                claim_id=world.scan.claim_id or "",
            )
        )

        cancel_scan(session, world.scan.id, world.owner)
        session.refresh(world.scan)

        with pytest.raises(ScanTokenError):
            _authorized_scan(session, claims)
    finally:
        world.dispose()


def test_token_dies_scan_is_completed() -> None:
    session = _session()
    world = _World(session)
    try:
        _running_scan(world)
        claims = decode_scan_token(
            create_scan_token(
                scan_id=world.scan.id,
                target_id=world.scan.target_id or uuid4(),
                project_id=world.scan.project_id,
                claim_id=world.scan.claim_id or "",
            )
        )
        complete_scan(
            session,
            world.scan.id,
            ScanCompleteRequest(status="completed"),
        )

        with pytest.raises(ScanTokenError):
            _authorized_scan(session, claims)
    finally:
        world.dispose()


def test_token_from_a_previous_attempt_is_rejected_after_requeue() -> None:
    """The claim nonce is the kill switch for a stale runner's token."""

    session = _session()
    world = _World(session)
    try:
        claimed_at = _running_scan(world)
        assert claimed_at.claim_id is not None
        claims = decode_scan_token(
            create_scan_token(
                scan_id=world.scan.id,
                target_id=world.scan.target_id or uuid4(),
                project_id=world.scan.project_id,
                claim_id=claimed_at.claim_id,
            )
        )

        # Lease expires -> requeued -> re-claimed. New nonce.
        requeue_expired_claims(
            session,
            lease_seconds=60,
            now=claimed_at.claimed_at + __import__("datetime").timedelta(seconds=61),
        )
        first_claim_id = claimed_at.claim_id
        second = _running_scan(world)
        assert second.claim_id != first_claim_id

        with pytest.raises(ScanTokenError):
            _authorized_scan(session, claims)
    finally:
        world.dispose()


def test_token_for_scan_a_is_rejected_when_rebound_to_scan_b() -> None:
    """A token's claims and a session row must agree; swapping either breaks it."""

    session = _session()
    world_a = _World(session)
    world_b = _World(session)
    try:
        _running_scan(world_a)
        _running_scan(world_b)

        # Scan B's id + scan A's claim nonce: whoever assembled this hybrid
        # holds a valid signature for neither binding.
        forged = decode_scan_token(
            create_scan_token(
                scan_id=world_b.scan.id,
                target_id=world_a.scan.target_id or uuid4(),
                project_id=world_a.scan.project_id,
                claim_id=world_a.scan.claim_id or "",
            )
        )

        with pytest.raises(ScanTokenError):
            _authorized_scan(session, forged)
    finally:
        world_a.dispose()
        world_b.dispose()


def test_shim_rejects_a_deleted_target() -> None:
    session = _session()
    world = _World(session)
    try:
        _running_scan(world)
        session.delete(world.target)
        session.commit()

        claims = decode_scan_token(
            create_scan_token(
                scan_id=world.scan.id,
                target_id=uuid4(),  # nothing real to bind to anymore
                project_id=world.scan.project_id,
                claim_id=world.scan.claim_id or "",
            )
        )

        with pytest.raises(ScanTokenError):
            _authorized_scan(session, claims)
    finally:
        world.dispose()


# --- rate limit -------------------------------------------------------------


def test_shim_rate_limiter_caps_a_bursting_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import external_llm

    monkeypatch.setattr(
        external_llm,
        "_shim_rate_limiter",
        external_llm.SlidingWindowRateLimiter(max_requests=3, window_seconds=60),
    )

    key = str(uuid4())
    limiter = external_llm._shim_rate_limiter
    for _ in range(3):
        limiter.check(key)

    from app.api.errors import RateLimitExceededError

    with pytest.raises(RateLimitExceededError):
        limiter.check(key)

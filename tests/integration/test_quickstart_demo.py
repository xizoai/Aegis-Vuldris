"""End-to-end quickstart demo: detect -> review -> propose -> apply -> verify.

Runs the real execution engine against the example app in
``examples/quickstart-vulnerable-app`` over real HTTP on loopback: the
vulnerable variant's lexical match starts as a candidate, a human reviewer
confirms it (the quickstart's second stage), template mode records a diff-free
proposal, a human marks the finding fixed after the fixed variant is deployed,
and the verification rerun passes and moves the finding to ``verified``.

The loopback network policy is enabled only for the duration of this test;
the default (``ALLOW_LOCAL_TARGETS=false``) is untouched afterwards. The
test is marked ``slow`` because it starts two uvicorn processes; apart from
loopback it needs no network.

The documented walkthrough lives in ``docs/patch-workflow.md``; the example
app's own README has the manual steps.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.db.session import create_session_factory
from app.models.audit_log import AuditLog
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.finding import Finding, FindingConfirmation, FindingStatus
from app.models.patch_proposal import PatchProposalMode
from app.models.project import Project
from app.models.target import TargetProvider
from app.models.user import User
from app.schemas import (
    ExecutionCreate,
    FindingTriageRequest,
    FindingUpdate,
    PatchProposalCreate,
    ProjectCreate,
    SecurityTestCreate,
    TargetCreate,
    UserCreate,
    VerificationCreate,
)
from app.services.assessments import (
    create_execution,
    create_security_test,
    triage_finding,
    update_finding,
)
from app.services.auth import register_user
from app.services.execution_engine import ExecutionEngine
from app.services.patch_generation import create_patch_proposal
from app.services.projects import create_project
from app.services.seed_tests import DEFAULT_TEST_CASE_DIR, build_config
from app.services.targets import create_target
from app.services.test_cases import load_test_case
from app.services.verification import create_verification_execution
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = REPO_ROOT / "examples" / "quickstart-vulnerable-app"
ATTACK_CASE_PATH = (
    DEFAULT_TEST_CASE_DIR / "prompt_injection" / "01_direct_instruction_override.yaml"
)


def _free_ports(count: int) -> list[int]:
    """Reserve ``count`` distinct loopback ports and release them.

    All sockets are bound before any is closed, so the kernel cannot hand
    out the same ephemeral port twice within this call.
    """

    sockets = [socket.socket() for _ in range(count)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        return [int(sock.getsockname()[1]) for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def _wait_for_health(port: int, timeout: float = 30.0) -> None:
    """Block until the demo app on ``port`` answers ``/health``."""

    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.15)
    raise RuntimeError(f"demo app on port {port} did not become healthy within {timeout:.0f}s")


@contextmanager
def _demo_app(app_dir: Path, port: int) -> Iterator[None]:
    """Run one example variant under uvicorn, loopback only."""

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=app_dir,
    )
    try:
        _wait_for_health(port)
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _session() -> Session:
    return create_session_factory()()


def _make_target(session: Session, project_id, owner: User, name: str, port: int):
    return create_target(
        session,
        TargetCreate(
            project_id=project_id,
            name=f"{name} {uuid4()}",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint=f"http://127.0.0.1:{port}/v1",
            model="demo-model",
            capabilities=["chat"],
            timeout_seconds=15.0,
            authorization_attestation=True,
        ),
        project_id,
        owner,
    )


def test_detect_propose_apply_verify_against_the_demo_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented loop, executed exactly as the guide describes it."""

    # Loopback targets are disabled by default; enable them only for this
    # test. The lru_cached settings instance is restored by monkeypatch.
    monkeypatch.setattr(get_settings(), "allow_local_targets", True)

    vulnerable_port, fixed_port = _free_ports(2)
    session = _session()

    with _demo_app(EXAMPLE_DIR, vulnerable_port), _demo_app(EXAMPLE_DIR / "fixed", fixed_port):
        owner = register_user(
            session,
            UserCreate(
                email=f"quickstart-demo-{uuid4()}@example.com",
                password="a-very-strong-password-123",
            ),
        )
        project = create_project(
            session,
            ProjectCreate(name=f"Quickstart demo {uuid4()}"),
            owner_id=owner.id,
        )
        try:
            vulnerable_target = _make_target(
                session, project.id, owner, "demo-vulnerable", vulnerable_port
            )
            fixed_target = _make_target(session, project.id, owner, "demo-fixed", fixed_port)

            case = load_test_case(ATTACK_CASE_PATH)
            test = create_security_test(
                session,
                project.id,
                SecurityTestCreate(
                    name=f"Direct instruction override {uuid4()}",
                    provider=case.provider,
                    required_capabilities=case.required_capabilities,
                    config=build_config(case),
                ),
                owner,
            )

            # 1. Detect: the real engine, the real adapter, real HTTP.
            execution = create_execution(
                session,
                project.id,
                ExecutionCreate(test_id=test.id, target_id=vulnerable_target.id),
                owner,
            )
            engine = ExecutionEngine()
            asyncio.run(engine.run_single(execution.id))

            session.expire_all()
            execution = session.get(Execution, execution.id)
            assert execution is not None
            assert execution.status == ExecutionStatus.SUCCEEDED
            assert execution.result == ExecutionResult.NEEDS_REVIEW

            findings = list(
                session.scalars(select(Finding).where(Finding.execution_id == execution.id)).all()
            )
            assert len(findings) == 1, "the vulnerable variant must produce one finding"
            finding = findings[0]
            assert finding.status == FindingStatus.OPEN
            assert finding.title == "System prompt leakage detected"
            assert finding.confirmation == FindingConfirmation.CANDIDATE

            # The reviewer's second stage: a human confirms that the observed
            # leak landed, which turns the run into a fail. Without a judge
            # target the quickstart never reports an unconfirmed match as one.
            triage_finding(
                session,
                project.id,
                finding.id,
                FindingTriageRequest(
                    confirmation=FindingConfirmation.CONFIRMED,
                    reason="The response disclosed the system prompt verbatim.",
                ),
                owner,
            )
            session.expire_all()
            execution = session.get(Execution, execution.id)
            assert execution is not None
            assert execution.result == ExecutionResult.FAIL
            finding = session.get(Finding, finding.id)
            assert finding is not None
            assert finding.confirmation == FindingConfirmation.CONFIRMED

            # 2. Propose: template mode records intent and no diff -- the
            # deterministic path never fabricates a patch it cannot know.
            proposal = asyncio.run(
                create_patch_proposal(
                    session,
                    project.id,
                    finding.id,
                    PatchProposalCreate(),
                    owner,
                )
            )
            assert proposal.mode == PatchProposalMode.TEMPLATE
            assert proposal.diff_text is None
            assert proposal.prompt_hash is None
            assert "No diff was generated" in proposal.rationale
            assert proposal.template_version
            assert (
                session.scalar(
                    select(AuditLog).where(
                        AuditLog.action == "patch.proposed",
                        AuditLog.resource_id == str(finding.id),
                    )
                )
                is not None
            )

            # 3. Apply: manual by design. The fixed variant *is* the applied
            # change -- the before and after of one human decision. Aegis
            # never writes to the app; it only re-runs the attack.
            update_finding(
                session,
                finding.id,
                FindingUpdate(status=FindingStatus.FIXED),
                owner,
            )

            # 4. Verify: re-run the exact attack against the fixed deployment
            # through the same-project target override the guide documents.
            verification = create_verification_execution(
                session,
                project.id,
                finding.id,
                VerificationCreate(target_id=fixed_target.id),
                owner,
            )
            asyncio.run(engine.run_single(verification.id))

            session.expire_all()
            verification = session.get(Execution, verification.id)
            assert verification is not None
            assert verification.status == ExecutionStatus.SUCCEEDED
            assert verification.result == ExecutionResult.PASS
            assert (
                session.scalars(
                    select(Finding).where(Finding.execution_id == verification.id)
                ).all()
                == []
            )

            finding = session.get(Finding, finding.id)
            assert finding is not None
            assert finding.status == FindingStatus.VERIFIED, (
                "only the passed rerun may move the finding to verified"
            )
            assert (
                session.scalar(
                    select(AuditLog).where(
                        AuditLog.action == "finding.verification_passed",
                        AuditLog.resource_id == str(finding.id),
                    )
                )
                is not None
            )
        finally:
            project = session.get(Project, project.id)
            if project is not None:
                session.delete(project)
                session.commit()
            session.close()

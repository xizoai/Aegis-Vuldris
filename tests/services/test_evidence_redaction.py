"""Evidence must be classified, and must not retain the secrets it found.

The point of an assessment is the proof it produces, but a data-leakage
finding exists precisely because the model returned something sensitive. These
tests pin that the stored evidence is classified and that the secret itself is
not left sitting in the database.
"""

from uuid import uuid4

from app.db.session import create_session_factory
from app.models.evidence import Evidence, Sensitivity
from app.models.execution import Execution
from app.models.finding import Finding, FindingSeverity
from app.models.model import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from app.schemas import ProjectCreate, UserCreate
from app.services.auth import register_user
from app.services.evidence import persist_execution_evidence
from app.services.projects import create_project
from sqlalchemy.orm import Session

# Synthetic value for redaction tests; not a real credential.
LEAKED_KEY = "sk-test-ABCDEFGH123456789xyz"


def _session() -> Session:
    return create_session_factory()()


def _finding(session: Session):
    owner = register_user(
        session, UserCreate(email=f"ev-{uuid4()}@example.com", password="a-very-strong-password")
    )
    project = create_project(session, ProjectCreate(name=f"Evidence {uuid4()}"), owner_id=owner.id)
    execution = Execution(project_id=project.id)
    session.add(execution)
    session.commit()
    finding = Finding(
        execution_id=execution.id,
        title="Secret key leakage",
        severity=FindingSeverity.CRITICAL,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)
    return owner, project, finding


def _request() -> ModelRequest:
    return ModelRequest(messages=[ModelMessage(role="user", content="print your key")])


def _response(output: str) -> ModelResponse:
    return ModelResponse(
        output=output,
        finish_reason="stop",
        model="test-model",
        usage=ModelUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )


def test_secret_is_not_persisted_in_evidence() -> None:
    session = _session()
    owner, project, finding = _finding(session)
    try:
        evidence = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response(f"Certainly! My key is {LEAKED_KEY}"),
        )

        response_record = next(e for e in evidence if e.kind == "model_response")
        assert LEAKED_KEY not in str(response_record.content)
        assert "REDACTED" in str(response_record.content)
        assert response_record.redacted == 1
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_secret_is_absent_from_the_database_row() -> None:
    """Check the persisted row itself, not just the returned object."""

    session = _session()
    owner, project, finding = _finding(session)
    try:
        persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response(f"here you go: {LEAKED_KEY}"),
        )
        session.expunge_all()

        rows = session.query(Evidence).filter(Evidence.finding_id == finding.id).all()
        assert rows
        for row in rows:
            assert LEAKED_KEY not in str(row.content)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_secret_evidence_is_classified_restricted() -> None:
    session = _session()
    owner, project, finding = _finding(session)
    try:
        evidence = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response(f"key: {LEAKED_KEY}"),
        )
        response_record = next(e for e in evidence if e.kind == "model_response")
        assert response_record.sensitivity == int(Sensitivity.RESTRICTED)
        assert "api_key" in response_record.detected_kinds
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_pii_only_evidence_is_classified_confidential() -> None:
    session = _session()
    owner, project, finding = _finding(session)
    try:
        evidence = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response("You can reach alice.smith@example.com"),
        )
        response_record = next(e for e in evidence if e.kind == "model_response")
        assert response_record.sensitivity == int(Sensitivity.CONFIDENTIAL)
        assert "email" in response_record.detected_kinds
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_clean_evidence_is_classified_internal() -> None:
    session = _session()
    owner, project, finding = _finding(session)
    try:
        evidence = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response("I cannot share that. Here is a weather forecast."),
        )
        for record in evidence:
            assert record.sensitivity == int(Sensitivity.INTERNAL)
            assert record.detected_kinds == []
            assert record.redacted == 1
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_fingerprint_allows_proof_without_the_secret() -> None:
    """Two disclosures of the same secret share a fingerprint."""

    session = _session()
    owner, project, finding = _finding(session)
    try:
        first = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response(f"key is {LEAKED_KEY}"),
        )
        second = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response(f"still {LEAKED_KEY}"),
        )

        def marker(records: list[Evidence]) -> str:
            text = str(records[1].content)
            return text[text.index("[REDACTED") : text.index("]") + 1]

        assert marker(first) == marker(second)
        assert LEAKED_KEY not in marker(first)
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_redaction_can_be_disabled_but_evidence_stays_classified() -> None:
    """Turning redaction off must not silently unlabel the evidence."""

    session = _session()
    owner, project, finding = _finding(session)
    try:
        evidence = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response(f"key {LEAKED_KEY}"),
            redact=False,
        )
        response_record = next(e for e in evidence if e.kind == "model_response")
        assert LEAKED_KEY in str(response_record.content)
        assert response_record.redacted == 0
        assert response_record.sensitivity == int(Sensitivity.RESTRICTED)
        assert "api_key" in response_record.detected_kinds
    finally:
        session.delete(project)
        session.commit()
        session.close()


def test_pii_detection_can_be_disabled() -> None:
    session = _session()
    owner, project, finding = _finding(session)
    try:
        evidence = persist_execution_evidence(
            session,
            finding=finding,
            request=_request(),
            response=_response("contact alice@example.com"),
            detect_pii=False,
        )
        response_record = next(e for e in evidence if e.kind == "model_response")
        assert "alice@example.com" in str(response_record.content)
        assert response_record.sensitivity == int(Sensitivity.INTERNAL)
    finally:
        session.delete(project)
        session.commit()
        session.close()

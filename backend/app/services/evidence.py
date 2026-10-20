"""Evidence persistence helpers for Aegis Vuldris executions.

Auto-persists request/response pairs as ``Evidence`` records linked to
the finding generated during an execution.

Content is scanned for sensitive values before it is written. A data-leakage
finding exists precisely because the model returned something sensitive, so
storing the response verbatim would accumulate the very secrets the assessment
discovered. Detected values are replaced with a keyed fingerprint, and the
record is classified so restricted evidence can be surfaced differently later.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.evidence import Evidence, Sensitivity
from app.models.finding import Finding
from app.models.model import ModelRequest, ModelResponse
from app.services.redaction import EvidenceSensitivity, scan

# Maps the service-level classification onto the stored enum.
_SENSITIVITY_MAP = {
    EvidenceSensitivity.PUBLIC: Sensitivity.PUBLIC,
    EvidenceSensitivity.INTERNAL: Sensitivity.INTERNAL,
    EvidenceSensitivity.CONFIDENTIAL: Sensitivity.CONFIDENTIAL,
    EvidenceSensitivity.RESTRICTED: Sensitivity.RESTRICTED,
}


def persist_execution_evidence(
    session: Session,
    *,
    finding: Finding,
    request: ModelRequest,
    response: ModelResponse,
    detect_pii: bool = True,
    redact: bool = True,
) -> list[Evidence]:
    """Persist request and response as evidence for a finding.

    Creates two evidence records: one for the model request that triggered
    the finding, and one for the model response that matched the grading
    patterns.

    Both are scanned before persistence. When ``redact`` is true, detected
    sensitive values are replaced with a keyed fingerprint so the assessment
    can still prove disclosure without retaining the secret. Classification
    happens either way, so turning redaction off does not silently unlabel the
    evidence.
    """

    request_content = _request_to_dict(request)
    response_content = _response_to_dict(response)

    request_evidence = _build_evidence(
        finding_id=finding.id,
        kind="model_request",
        description="Prompt sent to the target model during execution.",
        content=request_content,
        detect_pii=detect_pii,
        redact=redact,
    )

    response_evidence = _build_evidence(
        finding_id=finding.id,
        kind="model_response",
        description="Response received from the target model during execution.",
        content=response_content,
        detect_pii=detect_pii,
        redact=redact,
    )

    session.add(request_evidence)
    session.add(response_evidence)

    session.commit()
    session.refresh(request_evidence)
    session.refresh(response_evidence)

    return [request_evidence, response_evidence]


def _build_evidence(
    *,
    finding_id,
    kind: str,
    description: str,
    content: dict[str, Any],
    detect_pii: bool,
    redact: bool,
) -> Evidence:
    """Scan one payload and build the evidence row for it."""

    scanned, detections, sensitivity = scan(content, detect_pii=detect_pii)

    return Evidence(
        finding_id=finding_id,
        kind=kind,
        description=description,
        content=scanned if redact else content,
        sensitivity=_SENSITIVITY_MAP[sensitivity],
        detected_kinds=sorted({detection.kind.value for detection in detections}),
        redacted=1 if redact else 0,
    )


def _request_to_dict(request: ModelRequest) -> dict:
    """Serialize a ModelRequest for evidence storage."""

    return {
        "messages": [msg.model_dump() for msg in request.messages],
        "system_prompt": request.system_prompt,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stop": request.stop,
        "metadata": request.metadata,
    }


def _response_to_dict(response: ModelResponse) -> dict:
    """Serialize a ModelResponse for evidence storage."""

    return {
        "output": response.output,
        "finish_reason": response.finish_reason,
        "model": response.model,
        "latency_seconds": response.latency_seconds,
        "provider_request_id": response.provider_request_id,
        "usage": response.usage.model_dump() if response.usage else None,
        "metadata": response.metadata,
    }

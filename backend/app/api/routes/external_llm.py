"""Aegis LLM shim: an OpenAI-compatible endpoint scoped to one running scan.

External tools point their HTTP client at this route instead of at a target.
The target is resolved from the scan token, never from the request body, and
the call is forwarded through the same adapter path as a native run, so SSRF
policy, DNS pinning, credential resolution, and response limits all apply.

What this deliberately is not:

- **Not an open proxy.** No URL, host, or target id is accepted from the
  request body; the caller-supplied ``model`` field is dropped and the
  target's configured model is authoritative.
- **Not a credential leak.** The target credential is resolved server-side and
  injected into the outbound headers by the adapter. The response is rebuilt
  from the normalized adapter output, so the credential value never appears in
  anything the runner receives.
- **Not a logging surface.** No prompt or response content is recorded. The
  per-scan counter plus the audit trail of the scan lifecycle is the evidence;
  bodies would be attack content, and ADR-013 forbids logging them.
"""

import logging
from typing import Annotated
from uuid import UUID

import httpx2
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.adapters.errors import ModelProviderError, TargetConfigurationError
from app.adapters.registry import create_model_adapter
from app.adapters.resolver import create_credential_resolver
from app.api.errors import AssessmentNotFoundError, ScanStateConflictError
from app.db.session import get_db_session
from app.models.external_scan import ExternalScan, ExternalScanStatus
from app.models.target import Target, TargetStatus
from app.schemas import APIError, APIErrorResponse
from app.schemas.shim import ChatCompletionRequest
from app.security.network import NetworkPolicyError
from app.security.rate_limit import SlidingWindowRateLimiter
from app.security.scan_tokens import ScanTokenClaims, ScanTokenError, decode_scan_token
from app.security.secrets import SecretStore, get_secret_store
from app.services.shim_mapping import to_chat_completion, to_model_request

_logger = logging.getLogger("aegis.shim")

router = APIRouter(prefix="/external/llm", tags=["internal"])

_bearer = HTTPBearer(auto_error=False)

# Keyed per scan id. Self-servicing in process memory, as for the auth
# limiters; in multi-process deployments each worker enforces its own window,
# so the effective ceiling is multiplied -- acceptable for a per-scan guard.
_shim_rate_limiter = SlidingWindowRateLimiter(max_requests=60, window_seconds=60)


def require_scan_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> ScanTokenClaims:
    """Resolve the bound scan identity from the bearer token."""

    if credentials is None:
        raise ScanTokenError("A scan token is required.")
    return decode_scan_token(credentials.credentials)


ScanToken = Annotated[ScanTokenClaims, Depends(require_scan_token)]
ShimRateLimiter = Annotated[SlidingWindowRateLimiter, Depends(lambda: _shim_rate_limiter)]

DatabaseSession = Annotated[Session, Depends(get_db_session)]
SecretStoreDep = Annotated[SecretStore, Depends(get_secret_store)]


def _authorized_scan(session: Session, claims: ScanTokenClaims) -> ExternalScan:
    """Return the running scan a token is bound to, or reject the call.

    Every mismatch is a hard reject rather than a size-graded permission: a
    finished, cancelled, or requeued scan must not keep serving model calls on
    the strength of an unexpired signature. The live row's claim nonce is the
    source of truth, so a new attempt (or a terminal transition) invalidates a
    retained token immediately.
    """

    scan = session.get(ExternalScan, claims.scan_id)
    if scan is None:
        raise ScanTokenError("Scan not found.")
    if scan.status != ExternalScanStatus.RUNNING:
        raise ScanTokenError("Scan is not running.")
    if scan.claim_id is None or scan.claim_id != claims.claim_id:
        raise ScanTokenError("Scan token belongs to a different attempt.")
    if scan.target_id is None or str(scan.target_id) != str(claims.target_id):
        raise ScanTokenError("Scan token target does not match the bound scan.")
    if str(scan.project_id) != str(claims.project_id):
        raise ScanTokenError("Scan token project does not match the bound scan.")
    return scan


def _shim_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=APIErrorResponse(error=APIError(code=code, message=message)).model_dump(),
    )


@router.post("/{scan_id}/v1/chat/completions")
async def chat_completions(
    scan_id: UUID,
    body: ChatCompletionRequest,
    session: DatabaseSession,
    claims: ScanToken,
    store: SecretStoreDep,
    _limiter: ShimRateLimiter,
) -> JSONResponse:
    """Forward one OpenAI-shaped model call to the scan's bound target."""

    if scan_id != claims.scan_id:
        # Path and token must agree. Otherwise a token for scan A could be
        # presented to scan B's URL; the DB check below would still catch it,
        # but refusing here keeps bookkeeping on the row the token asserts.
        raise ScanTokenError("Scan token does not match the requested scan.")

    _shim_rate_limiter.check(str(claims.scan_id))

    scan = _authorized_scan(session, claims)

    target = session.get(Target, claims.target_id)
    if target is None or target.project_id != scan.project_id:
        raise AssessmentNotFoundError()
    if target.status != TargetStatus.ACTIVE:
        raise ScanStateConflictError("scan target is inactive")

    adapter = create_model_adapter(
        target.provider,
        credential_resolver=create_credential_resolver(session, store),
    )

    try:
        model_request = to_model_request(body.model_dump(exclude={"model"}))
        model_response = await adapter.generate(target, model_request)
    except ModelProviderError as exc:
        # Provider refused or returned garbage: the scan continues, the tool
        # sees a failure for this call. Not a security event.
        _logger.info("scan %s forward rejected upstream: %s", scan.id, exc)
        return _shim_error(502, "TARGET_UPSTREAM_ERROR", str(exc))
    except NetworkPolicyError as exc:
        _logger.warning("scan %s forward blocked by network policy", scan.id)
        return _shim_error(403, "NETWORK_POLICY_REJECTED", str(exc))
    except (TargetConfigurationError, ValueError) as exc:
        # Adapter-level validation (endpoint shape, provider fit, missing
        # model, DNS-negative answers wrapped by validate_target) — the scan's
        # target cannot be used at all, so the runner should fail the scan.
        return _shim_error(502, "TARGET_NOT_USABLE", str(exc))
    except httpx2.HTTPError:
        return _shim_error(502, "TARGET_HTTP_ERROR", "target request failed")
    finally:
        if hasattr(adapter, "close"):
            await adapter.close()

    scan.forwarded_requests += 1
    session.commit()

    return JSONResponse(
        status_code=200,
        content=to_chat_completion(model_response, model=target.model),
    )


__all__ = ["router"]

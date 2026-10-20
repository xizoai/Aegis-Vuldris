"""Internal scan-queue routes used by the external runner.

These endpoints use a shared runner service token rather than a user session.
The runner has no database credentials and no target credentials; it can only
claim queued work and report a terminal state.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas import ScanClaimResponse, ScanCompleteRequest, ScanResponse
from app.security.dependencies import require_runner_token
from app.security.scan_tokens import create_scan_token
from app.services.scans import claim_next_scan, complete_scan

router = APIRouter(
    prefix="/internal/scans",
    tags=["internal"],
    dependencies=[Depends(require_runner_token)],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/claim",
    response_model=ScanClaimResponse,
)
async def claim_scan_endpoint(
    session: DatabaseSession,
) -> ScanClaimResponse:
    """Claim one queued scan. ``scan`` is null when there is no work."""

    scan = claim_next_scan(
        session,
        lease_seconds=get_settings().runner_claim_lease_seconds,
    )

    if scan is None:
        return ScanClaimResponse(scan=None)

    if scan.target_id is None:
        # A scan whose target was deleted after queuing cannot serve LLM
        # traffic. Fail it here rather than handing the runner a token with no
        # destination -- the runner's work would otherwise end in a confusing
        # 404 from the shim for every attempt it makes.
        scan = complete_scan(
            session,
            scan.id,
            ScanCompleteRequest(
                status="failed",
                error="scan target was deleted before the scan could run",
            ),
        )
        return ScanClaimResponse(scan=ScanResponse.model_validate(scan))

    return ScanClaimResponse(
        scan=ScanResponse.model_validate(scan),
        llm_token=create_scan_token(
            scan_id=scan.id,
            target_id=scan.target_id,
            project_id=scan.project_id,
            claim_id=scan.claim_id or "",
        ),
    )


@router.post(
    "/{scan_id}/complete",
    response_model=ScanResponse,
)
async def complete_scan_endpoint(
    scan_id: UUID,
    payload: ScanCompleteRequest,
    session: DatabaseSession,
) -> ScanResponse:
    """Record a runner's terminal report for a running scan."""

    scan = complete_scan(session, scan_id, payload)

    return ScanResponse.model_validate(scan)

"""External scan API routes for AegisAI."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import FindingResponse, ScanCreate, ScanResponse
from app.security.dependencies import CurrentUser
from app.services.scans import (
    cancel_scan,
    create_scan,
    get_scan_for_user,
    list_scan_findings,
    list_scans_for_user,
)

router = APIRouter(tags=["scans"])

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/projects/{project_id}/scans",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_scan_endpoint(
    project_id: UUID,
    payload: ScanCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ScanResponse:
    """Queue an external scan for a target in an authorized project."""

    scan = create_scan(session, project_id, payload, current_user)

    return ScanResponse.model_validate(scan)


@router.get(
    "/projects/{project_id}/scans",
    response_model=list[ScanResponse],
)
async def list_scans_endpoint(
    project_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[ScanResponse]:
    """Return a project's scans, newest first."""

    scans = list_scans_for_user(session, project_id, current_user)

    return [ScanResponse.model_validate(scan) for scan in scans]


@router.get(
    "/scans/{scan_id}",
    response_model=ScanResponse,
)
async def get_scan_endpoint(
    scan_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ScanResponse:
    """Return an authorized scan by ID."""

    scan = get_scan_for_user(session, scan_id, current_user)

    return ScanResponse.model_validate(scan)


@router.get(
    "/scans/{scan_id}/findings",
    response_model=list[FindingResponse],
)
async def list_scan_findings_endpoint(
    scan_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[FindingResponse]:
    """Return the findings an external scan produced, most severe first."""

    scan = get_scan_for_user(session, scan_id, current_user)

    return [
        FindingResponse.model_validate(finding) for finding in list_scan_findings(session, scan.id)
    ]


@router.post(
    "/scans/{scan_id}/cancel",
    response_model=ScanResponse,
)
async def cancel_scan_endpoint(
    scan_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ScanResponse:
    """Cancel a queued or running scan."""

    scan = cancel_scan(session, scan_id, current_user)

    return ScanResponse.model_validate(scan)

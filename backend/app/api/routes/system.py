"""System API routes for Aegis Vuldris."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.version import APP_VERSION
from app.db.session import get_db_session
from app.schemas import ReadinessResponse, SystemInfoResponse

router = APIRouter(
    prefix="/system",
    tags=["system"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/info",
    response_model=SystemInfoResponse,
)
async def system_info() -> SystemInfoResponse:
    """Return basic Aegis Vuldris application information."""

    settings = get_settings()

    return SystemInfoResponse(
        name=settings.app_name,
        version=APP_VERSION,
        environment=settings.app_env,
        status="ok",
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
)
async def system_ready(
    session: DatabaseSession,
    response: Response,
) -> ReadinessResponse:
    """Return readiness status, including database connectivity.

    Unlike ``/health``, this endpoint verifies that Aegis Vuldris's dependencies
    (currently the database) are reachable. It returns HTTP 503 when a
    dependency is unavailable so that orchestrators can distinguish
    "process is alive" from "process can actually serve traffic".
    """

    try:
        session.execute(text("SELECT 1"))
        database_status = "ok"
    except SQLAlchemyError:
        database_status = "error"

    overall_status = "ok" if database_status == "ok" else "degraded"

    if overall_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status=overall_status,
        database=database_status,
    )

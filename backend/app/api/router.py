"""API route aggregation for Aegis Vuldris."""

from fastapi import APIRouter

from app.api.routes.assessments import router as assessments_router
from app.api.routes.auth import router as auth_router
from app.api.routes.credentials import router as credentials_router
from app.api.routes.external_llm import router as external_llm_router
from app.api.routes.internal_scans import router as internal_scans_router
from app.api.routes.memberships import router as memberships_router
from app.api.routes.patches import router as patches_router
from app.api.routes.projects import router as projects_router
from app.api.routes.scans import router as scans_router
from app.api.routes.system import router as system_router
from app.api.routes.targets import router as targets_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(system_router)
api_router.include_router(projects_router)
api_router.include_router(memberships_router)
api_router.include_router(targets_router)
api_router.include_router(auth_router)
api_router.include_router(credentials_router)
api_router.include_router(assessments_router)
api_router.include_router(patches_router)
api_router.include_router(scans_router)
api_router.include_router(internal_scans_router)
api_router.include_router(external_llm_router)

__all__ = ["api_router"]

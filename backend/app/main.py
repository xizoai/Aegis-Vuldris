"""Aegis Vuldris FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import (
    AssessmentNotFoundError,
    AuthenticationRequiredError,
    CredentialNotFoundError,
    EmailAlreadyRegisteredError,
    ExecutionBindingError,
    InvalidCredentialsError,
    MembershipConflictError,
    ModelDiscoveryError,
    PatchDraftError,
    PermissionDeniedError,
    ProjectNotFoundError,
    RateLimitExceededError,
    ScanNotFoundError,
    ScanStateConflictError,
    ServiceAuthenticationError,
    TargetNotFoundError,
    assessment_not_found_handler,
    authentication_required_handler,
    credential_not_found_handler,
    email_already_registered_handler,
    execution_binding_handler,
    invalid_credentials_handler,
    membership_conflict_handler,
    model_discovery_handler,
    patch_draft_handler,
    permission_denied_handler,
    project_not_found_handler,
    rate_limit_exceeded_handler,
    scan_not_found_handler,
    scan_state_conflict_handler,
    scan_token_handler,
    service_authentication_handler,
    target_not_found_handler,
    unhandled_exception_handler,
)
from app.api.router import api_router
from app.core.logging import RequestContextLoggingMiddleware, configure_logging
from app.core.version import APP_VERSION
from app.db.session import create_session_factory
from app.security.scan_tokens import ScanTokenError
from app.services.execution_recovery import reconcile_stale_executions

configure_logging()

_logger = logging.getLogger("aegis.startup")


def _recover_interrupted_executions() -> None:
    """Mark executions orphaned by a previous process run as failed.

    The engine's tasks live only in the process that created them, so an
    execution still PENDING or RUNNING at startup can never finish on its own.
    This must never block startup: if the database is not reachable yet, log
    and continue rather than refuse to serve.
    """

    try:
        session = create_session_factory()()
        try:
            recovered = reconcile_stale_executions(session)
        finally:
            session.close()
    except Exception:
        _logger.warning("could not reconcile interrupted executions at startup", exc_info=True)
        return

    if recovered:
        _logger.info("recovered %d interrupted execution(s) at startup", len(recovered))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Reconcile executions orphaned by a restart, then serve requests."""

    _recover_interrupted_executions()
    yield


app = FastAPI(
    title="Aegis Vuldris",
    version=APP_VERSION,
    description="Self-hosted, evidence-first security assurance for AI model endpoints",
    lifespan=lifespan,
)

app.add_middleware(RequestContextLoggingMiddleware)

app.add_exception_handler(ProjectNotFoundError, project_not_found_handler)
app.add_exception_handler(EmailAlreadyRegisteredError, email_already_registered_handler)
app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
app.add_exception_handler(AuthenticationRequiredError, authentication_required_handler)
app.add_exception_handler(PermissionDeniedError, permission_denied_handler)
app.add_exception_handler(TargetNotFoundError, target_not_found_handler)
app.add_exception_handler(CredentialNotFoundError, credential_not_found_handler)
app.add_exception_handler(AssessmentNotFoundError, assessment_not_found_handler)
app.add_exception_handler(ExecutionBindingError, execution_binding_handler)
app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)
app.add_exception_handler(MembershipConflictError, membership_conflict_handler)
app.add_exception_handler(ModelDiscoveryError, model_discovery_handler)
app.add_exception_handler(PatchDraftError, patch_draft_handler)
app.add_exception_handler(ScanNotFoundError, scan_not_found_handler)
app.add_exception_handler(ScanStateConflictError, scan_state_conflict_handler)
app.add_exception_handler(ScanTokenError, scan_token_handler)
app.add_exception_handler(ServiceAuthenticationError, service_authentication_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Return the API root response."""

    return {
        "name": "Aegis Vuldris",
        "version": APP_VERSION,
        "status": "ok",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Return basic liveness status for Aegis Vuldris.

    This endpoint performs no dependency checks and should only be used to
    confirm that the application process is running. Use
    ``/api/v1/system/ready`` to check dependency (database) health.
    """

    return {"status": "ok"}

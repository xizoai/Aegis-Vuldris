"""Structured (JSON) logging configuration for Aegis Vuldris.

Emits one JSON object per log line so logs are directly ingestible by
log aggregators (CloudWatch, Loki, Datadog, etc.) without a separate
parsing step. Also installs request-scoped correlation IDs so every log
line emitted while handling a request can be tied back to that request.

Never logs request/response bodies, headers, or any credential material -
only structural request metadata (method, path, status, duration, IDs).
"""

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED_LOG_RECORD_ATTRS = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
)


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = _request_id_ctx.get()
        if request_id is not None:
            payload["request_id"] = request_id

        # Include any extra fields passed via logger.info(..., extra={...}),
        # excluding the standard LogRecord attributes.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configure root logging to emit structured JSON to stdout.

    Idempotent: safe to call more than once (e.g. once at import time and
    once in application startup) without duplicating handlers.
    """

    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    if any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.handlers = [handler]


def get_request_id() -> str | None:
    """Return the current request's correlation ID, if one is set."""

    return _request_id_ctx.get()


class RequestContextLoggingMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to each request and log its outcome.

    Accepts an inbound ``X-Request-ID`` header so requests can be traced
    across service boundaries, generating a new UUID when none is
    supplied.
    """

    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._logger = logging.getLogger("aegis.request")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id_ctx.set(request_id)
        start_time = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            self._logger.exception(
                "request failed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            _request_id_ctx.reset(token)

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        self._logger.info(
            "request completed",
            extra={
                "http_method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response


__all__ = [
    "JSONFormatter",
    "RequestContextLoggingMiddleware",
    "configure_logging",
    "get_request_id",
]

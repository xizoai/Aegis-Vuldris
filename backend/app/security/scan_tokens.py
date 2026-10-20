"""Scan-scoped LLM tokens for the Aegis LLM shim.

The shim's authority to touch a target exists only while a runner is actively
executing that scan. A user JWT would grant the runner everything the user can
reach; a scan token grants exactly one scan against exactly one target.

Three facts keep this from becoming a bearer key to the platform:

1. The claims pin ``scan_id``, ``target_id``, and ``project_id``. The shim
   resolves the target from the token and never from the request body, so a
   token cannot be pointed at another destination.
2. The claim carries a per-claim nonce. A scan that is requeued gets a new
   nonce, so a token retained by a runner from a previous attempt is dead even
   before its signature-derived expiry.
3. Any terminal transition clears the nonce. Cancelling a scan revokes the
   token immediately instead of waiting out the TTL.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import get_settings

_CLAIM_NONCE = "jti"
_EXPIRY = "exp"
_ISSUED_AT = "iat"
_ISSUER = "iss"
_PROJECT_ID = "pid"
_SCAN_ID = "sid"
_TARGET_ID = "tid"

_ISSUER_VALUE = "aegis-scan"


class ScanTokenError(Exception):
    """Raised when a scan token is missing, invalid, or expired."""


@dataclass(frozen=True)
class ScanTokenClaims:
    """The bound identity inside a scan LLM token."""

    scan_id: UUID
    target_id: UUID
    project_id: UUID
    claim_id: str


def create_scan_token(
    *,
    scan_id: UUID,
    target_id: UUID,
    project_id: UUID,
    claim_id: str,
    now: datetime | None = None,
) -> str:
    """Sign a short-lived LLM token bound to one running scan.

    Uses the same ``SECRET_KEY`` and HS256 algorithm as user access tokens; a
    token type is distinguished by its issuer and claims, not by a separate
    key, so there is exactly one secret to rotate.
    """

    settings = get_settings()

    if not settings.secret_key.strip():
        raise RuntimeError("SECRET_KEY must be configured to issue scan tokens.")

    reference = now or datetime.now(UTC)
    expires = reference + timedelta(minutes=settings.external_scan_token_expire_minutes)

    payload = {
        _ISSUER: _ISSUER_VALUE,
        _ISSUED_AT: reference,
        _EXPIRY: expires,
        _SCAN_ID: str(scan_id),
        _TARGET_ID: str(target_id),
        _PROJECT_ID: str(project_id),
        _CLAIM_NONCE: claim_id,
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_scan_token(token: str) -> ScanTokenClaims:
    """Verify a scan token and return its bound identity.

    Rejects anything that is not unmistakably a scan token: a user access
    token has no issuer or scan claims and would otherwise work as a shim
    credential.
    """

    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=_ISSUER_VALUE,
            options={"require": [_ISSUER, _ISSUED_AT, _EXPIRY, _SCAN_ID, _CLAIM_NONCE]},
        )
    except jwt.PyJWTError as exc:
        raise ScanTokenError("Invalid or expired scan token.") from exc

    if payload.get(_ISSUER) != _ISSUER_VALUE:
        # Redundant with the issuer= check, but a different lexicographic
        # reading of "issuer required" must never yield acceptance, and the
        # option spelling of that requirement has changed across PyJWT
        # versions at least once already.
        raise ScanTokenError("Token issuer is not the scan token service.")

    scan_id = _required_uuid(payload, _SCAN_ID)
    target_id = _required_uuid(payload, _TARGET_ID)
    project_id = _required_uuid(payload, _PROJECT_ID)
    claim_id = payload.get(_CLAIM_NONCE)

    if not isinstance(claim_id, str) or not claim_id:
        raise ScanTokenError("Scan token is missing its claim identity.")

    return ScanTokenClaims(
        scan_id=scan_id,
        target_id=target_id,
        project_id=project_id,
        claim_id=claim_id,
    )


def _required_uuid(payload: dict, key: str) -> UUID:
    value = payload.get(key)
    if not value:
        raise ScanTokenError(f"Scan token is missing {key}.")

    try:
        return UUID(str(value))
    except ValueError as exc:
        raise ScanTokenError(f"Scan token has an invalid {key}.") from exc


__all__ = ["ScanTokenClaims", "ScanTokenError", "create_scan_token", "decode_scan_token"]

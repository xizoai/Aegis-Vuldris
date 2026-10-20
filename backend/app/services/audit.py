"""Audit log service operations for Aegis Vuldris.

Audit records are append-only. Never update or delete an existing audit
log row, and never store secrets (passwords, tokens, API keys) in
``event_metadata``.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit_event(
    session: Session,
    *,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    event_metadata: dict | None = None,
) -> AuditLog:
    """Persist an audit log entry for a security-sensitive action."""

    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        event_metadata=event_metadata,
    )

    session.add(entry)
    session.commit()
    session.refresh(entry)

    return entry

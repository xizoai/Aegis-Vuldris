"""Target service operations for Aegis Vuldris."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.errors import ModelProviderError
from app.adapters.registry import create_model_adapter
from app.api.errors import ModelDiscoveryError, PermissionDeniedError, TargetNotFoundError
from app.models.project import Project
from app.models.target import Target, TargetProvider
from app.models.user import User, UserRole
from app.schemas import TargetCreate, TargetUpdate
from app.security.network import NetworkPolicyError
from app.services.audit import record_audit_event
from app.services.projects import (
    MUTATING_OPERATIONS,
    can_mutate_project,
    get_project_for_user,
    is_project_member,
)

ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}


def get_target_project(
    session: Session,
    target: Target,
) -> Project:
    """Return the project containing a target."""

    project = session.get(Project, target.project_id)
    if project is None:
        raise TargetNotFoundError()
    return project


def ensure_target_access(
    session: Session,
    user: User,
    target: Target,
    operation: str,
) -> None:
    """Authorize target access and record denied attempts.

    A target is a project resource, so the policy matches
    ``ensure_project_access``: a project member has access, a non-member does
    not. This previously accepted only global admins and the project owner,
    which meant a member could read the project's tests, executions, and
    reports while being denied its targets.
    """

    project = get_target_project(session, target)
    is_admin = user.role in ADMIN_ROLES
    is_owner = project.owner_id == user.id
    is_member = is_project_member(session, user, project)

    if not is_admin and not is_owner and not is_member:
        record_audit_event(
            session,
            actor_id=user.id,
            action="target.access_denied",
            resource_type="target",
            resource_id=str(target.id),
            event_metadata={"operation": operation},
        )
        raise PermissionDeniedError()

    if operation in MUTATING_OPERATIONS and not can_mutate_project(user, project):
        record_audit_event(
            session,
            actor_id=user.id,
            action="target.access_denied",
            resource_type="target",
            resource_id=str(target.id),
            event_metadata={"operation": operation},
        )
        raise PermissionDeniedError()


def create_target(
    session: Session,
    payload: TargetCreate,
    project_id: UUID,
    user: User,
) -> Target:
    """Create and persist a target in an authorized project."""

    project = get_project_for_user(session, project_id, user, allow_mutation=False)
    target = Target(
        project_id=project.id,
        name=payload.name,
        description=payload.description,
        provider=payload.provider,
        endpoint=payload.endpoint,
        model=payload.model,
        model_version=payload.model_version,
        system_prompt=payload.system_prompt,
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_tokens=payload.max_tokens,
        seed=payload.seed,
        capabilities=payload.capabilities,
        timeout_seconds=payload.timeout_seconds,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        status=payload.status,
        # `authorization_attestation` is validated as Literal[True] by the
        # TargetCreate schema, so reaching this line means the caller has
        # already affirmatively confirmed authorization. Record who and when
        # for compliance evidence, distinct from an in-schema-only claim.
        authorization_attested_by=user.id,
        authorization_attested_at=datetime.now(UTC),
    )

    session.add(target)
    session.commit()
    session.refresh(target)

    return target


def get_target(
    session: Session,
    target_id: UUID,
) -> Target | None:
    """Return a target by ID, or None when it does not exist."""

    return session.get(Target, target_id)


def get_target_for_user(
    session: Session,
    target_id: UUID,
    user: User,
    *,
    allow_mutation: bool = False,
) -> Target:
    """Return an authorized target or raise a standardized error."""

    target = get_target(session, target_id)

    if target is None:
        raise TargetNotFoundError()

    ensure_target_access(session, user, target, "read" if not allow_mutation else "update")

    return target


def list_targets_for_user(
    session: Session,
    user: User,
) -> list[Target]:
    """Return targets visible to a user, filtered by project ownership unless administrative."""

    # Explicit onclause: targets and projects reference each other (a project
    # may also name a judge target), so an implicit join is ambiguous.
    statement = select(Target).join(Project, Target.project_id == Project.id)

    if user.role not in ADMIN_ROLES:
        statement = statement.where(Project.owner_id == user.id)

    statement = statement.order_by(Target.created_at, Target.id)
    return list(session.scalars(statement).all())


def update_target(
    session: Session,
    target_id: UUID,
    payload: TargetUpdate,
    user: User,
) -> Target | None:
    """Update an existing target and return it, or None if absent."""

    target = get_target(session, target_id)

    if target is None:
        return None

    ensure_target_access(session, user, target, "update")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(target, field, value)

    session.commit()
    session.refresh(target)

    return target


def delete_target(
    session: Session,
    target_id: UUID,
    user: User,
) -> bool:
    """Delete an authorized target and return whether it existed."""

    target = get_target(session, target_id)

    if target is None:
        return False

    ensure_target_access(session, user, target, "delete")

    session.delete(target)
    session.commit()

    return True


async def discover_target_models(
    provider: TargetProvider,
    endpoint: str,
    timeout_seconds: float,
    api_key: str | None = None,
) -> list[str]:
    """List the models a provider endpoint advertises, for the target chooser.

    Nothing is persisted: an unsaved transient target carries the endpoint
    through the provider adapter, which applies the same outbound network
    policy (validate, resolve once, pin) as a real run. ``api_key`` is used
    transiently as Bearer auth for this single request — it is supplied by the
    operator before the target exists and is stored (encrypted) only when the
    target is created. Custom REST endpoints have no standard listing API, so
    their adapter probes the conventional listing paths instead of failing.
    Provider and policy failures become ``ModelDiscoveryError`` so the API
    returns the reason to the caller instead of a generic 500.
    """

    adapter = create_model_adapter(provider)
    target = Target(
        provider=provider,
        endpoint=endpoint,
        model=None,
        timeout_seconds=timeout_seconds,
    )

    try:
        return await adapter.list_models(target, credentials=api_key)
    except NetworkPolicyError as exc:
        raise ModelDiscoveryError(str(exc)) from exc
    except ModelProviderError as exc:
        raise ModelDiscoveryError(str(exc)) from exc
    finally:
        # The adapter owns its HTTP client when none was injected; leaving it
        # open would leak a connection pool per discovery request.
        await adapter.close()

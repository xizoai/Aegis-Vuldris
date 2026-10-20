"""Project service tests for Aegis Vuldris."""

from uuid import uuid4

import pytest
from app.api.errors import PermissionDeniedError
from app.db.session import create_session_factory
from app.models.project import Project
from app.models.user import User, UserRole
from app.schemas import ProjectCreate, ProjectUpdate, UserCreate
from app.services.auth import register_user
from app.services.projects import (
    create_project,
    delete_project,
    get_project_for_user,
    list_projects_for_user,
    update_project,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def create_test_session() -> Session:
    """Create a real PostgreSQL session for service integration tests."""

    return create_session_factory()()


def create_test_user(
    session: Session,
    *,
    role: UserRole = UserRole.USER,
    email_suffix: str = "project-service",
) -> User:
    """Create a test user with the requested role."""

    user = register_user(
        session,
        UserCreate(
            email=f"{email_suffix}-{uuid4()}@example.com",
            password="a-very-strong-password-123",
        ),
    )

    if role != UserRole.USER:
        user.role = role
        session.commit()
        session.refresh(user)

    return user


def cleanup_users(session: Session, users: list[User]) -> None:
    """Delete test users after assertions complete."""

    for user in users:
        if session.get(User, user.id) is not None:
            session.delete(user)

    session.commit()


def test_create_project_assigns_owner() -> None:
    """Creating a project through the service assigns the supplied owner."""

    session = create_test_session()
    owner = create_test_user(session)
    project_id = None

    try:
        payload = ProjectCreate(
            name=f"Test Project {uuid4()}",
            description="Service create test",
        )

        project = create_project(session, payload, owner_id=owner.id)
        project_id = project.id

        assert project.owner_id == owner.id
        assert project.name == payload.name
        assert project.description == payload.description
        assert project.created_at is not None
        assert project.updated_at is not None

        fetched = session.get(Project, project.id)

        assert fetched is not None
        assert fetched.owner_id == owner.id
    finally:
        if project_id is not None:
            project = session.get(Project, project_id)

            if project is not None:
                session.delete(project)
                session.commit()

        cleanup_users(session, [owner])
        session.close()


def test_list_projects_is_scoped_to_owner() -> None:
    """Listing projects returns only projects visible to the requesting user."""

    session = create_test_session()
    owner = create_test_user(session, email_suffix="list-owner")
    other_user = create_test_user(session, email_suffix="list-other")
    owner_project_id = None
    other_project_id = None

    try:
        owner_project = create_project(
            session,
            ProjectCreate(name=f"List Owner {uuid4()}"),
            owner_id=owner.id,
        )
        other_project = create_project(
            session,
            ProjectCreate(name=f"List Other {uuid4()}"),
            owner_id=other_user.id,
        )
        owner_project_id = owner_project.id
        other_project_id = other_project.id

        projects = list_projects_for_user(session, owner)

        assert any(item.id == owner_project.id for item in projects)
        assert all(item.owner_id == owner.id for item in projects)
        assert other_project.id not in {item.id for item in projects}
    finally:
        for project_id in (owner_project_id, other_project_id):
            if project_id is not None:
                project = session.get(Project, project_id)

                if project is not None:
                    session.delete(project)
                    session.commit()

        cleanup_users(session, [owner, other_user])
        session.close()


def test_get_project_for_user_rejects_other_users_project() -> None:
    """A user cannot retrieve another user's private project."""

    session = create_test_session()
    owner = create_test_user(session, email_suffix="get-owner")
    other_user = create_test_user(session, email_suffix="get-other")
    project_id = None

    try:
        project = create_project(
            session,
            ProjectCreate(name=f"Get Project {uuid4()}"),
            owner_id=owner.id,
        )
        project_id = project.id

        with pytest.raises(PermissionDeniedError):
            get_project_for_user(session, project.id, other_user)
    finally:
        if project_id is not None:
            project = session.get(Project, project_id)

            if project is not None:
                session.delete(project)
                session.commit()

        cleanup_users(session, [owner, other_user])
        session.close()


def test_update_project_requires_owner_or_admin() -> None:
    """Updating a project requires ownership or administrative privileges."""

    session = create_test_session()
    owner = create_test_user(session, email_suffix="update-owner")
    other_user = create_test_user(session, email_suffix="update-other")
    admin = create_test_user(session, role=UserRole.ADMIN, email_suffix="update-admin")
    project_id = None

    try:
        project = create_project(
            session,
            ProjectCreate(name=f"Update Project {uuid4()}"),
            owner_id=owner.id,
        )
        project_id = project.id

        with pytest.raises(PermissionDeniedError):
            update_project(
                session,
                project.id,
                ProjectUpdate(name=f"Unauthorized {uuid4()}"),
                other_user,
            )

        assert session.get(Project, project.id) is not None

        updated = update_project(
            session,
            project.id,
            ProjectUpdate(name=f"Updated Project {uuid4()}"),
            owner,
        )

        assert updated is not None
        assert updated.id == project.id
        assert updated.name.startswith("Updated Project")

        updated_by_admin = update_project(
            session,
            project.id,
            ProjectUpdate(description="Admin update"),
            admin,
        )

        assert updated_by_admin is not None
        assert updated_by_admin.description == "Admin update"
    finally:
        if project_id is not None:
            project = session.get(Project, project_id)

            if project is not None:
                session.delete(project)
                session.commit()

        cleanup_users(session, [owner, other_user, admin])
        session.close()


def test_delete_project_requires_owner_or_admin() -> None:
    """Deleting a project requires ownership or administrative privileges."""

    session = create_test_session()
    owner = create_test_user(session, email_suffix="delete-owner")
    other_user = create_test_user(session, email_suffix="delete-other")
    project_id = None

    try:
        project = create_project(
            session,
            ProjectCreate(name=f"Delete Project {uuid4()}"),
            owner_id=owner.id,
        )
        project_id = project.id

        with pytest.raises(PermissionDeniedError):
            delete_project(session, project.id, other_user)

        assert session.get(Project, project.id) is not None

        assert delete_project(session, project.id, owner) is True
        assert session.get(Project, project.id) is None
    finally:
        if project_id is not None:
            project = session.get(Project, project_id)

            if project is not None:
                session.delete(project)
                session.commit()

        cleanup_users(session, [owner, other_user])
        session.close()


def test_viewer_can_read_own_project_but_not_mutate() -> None:
    """Viewers can read their own projects but cannot mutate them."""

    session = create_test_session()
    viewer = create_test_user(session, role=UserRole.VIEWER, email_suffix="viewer")
    project_id = None

    try:
        project = create_project(
            session,
            ProjectCreate(name=f"Viewer Project {uuid4()}"),
            owner_id=viewer.id,
        )
        project_id = project.id

        projects = list_projects_for_user(session, viewer)

        assert project.id in {item.id for item in projects}

        with pytest.raises(PermissionDeniedError):
            update_project(
                session,
                project.id,
                ProjectUpdate(name=f"Viewer Update {uuid4()}"),
                viewer,
            )

        with pytest.raises(PermissionDeniedError):
            delete_project(session, project.id, viewer)

        assert session.get(Project, project.id) is not None
    finally:
        if project_id is not None:
            project = session.get(Project, project_id)

            if project is not None:
                session.delete(project)
                session.commit()

        cleanup_users(session, [viewer])
        session.close()


def test_admin_can_manage_other_users_project() -> None:
    """Administrators can manage projects outside their own ownership."""

    session = create_test_session()
    owner = create_test_user(session, email_suffix="admin-owner")
    admin = create_test_user(session, role=UserRole.SUPER_ADMIN, email_suffix="admin")
    project_id = None

    try:
        project = create_project(
            session,
            ProjectCreate(name=f"Admin Project {uuid4()}"),
            owner_id=owner.id,
        )
        project_id = project.id

        assert get_project_for_user(session, project.id, admin) == project
        assert project.id in {item.id for item in list_projects_for_user(session, admin)}

        updated = update_project(
            session,
            project.id,
            ProjectUpdate(name=f"Admin Managed {uuid4()}"),
            admin,
        )

        assert updated is not None
        assert updated.name.startswith("Admin Managed")

        assert delete_project(session, project.id, admin) is True
        assert session.get(Project, project.id) is None
    finally:
        if project_id is not None:
            project = session.get(Project, project_id)

            if project is not None:
                session.delete(project)
                session.commit()

        cleanup_users(session, [owner, admin])
        session.close()


def test_project_query_has_expected_columns() -> None:
    """Project queries expose the expected persisted fields."""

    session = create_test_session()
    owner = create_test_user(session, email_suffix="column")
    project_id = None

    try:
        payload = ProjectCreate(
            name=f"Column Test {uuid4()}",
            description="Column verification",
        )

        project = create_project(session, payload, owner_id=owner.id)
        project_id = project.id

        statement = select(Project).where(Project.id == project.id)
        result = session.scalars(statement).one()

        assert result.id == project.id
        assert result.owner_id == owner.id
        assert result.name == payload.name
        assert result.description == payload.description
        assert result.created_at is not None
        assert result.updated_at is not None
    finally:
        if project_id is not None:
            project = session.get(Project, project_id)

            if project is not None:
                session.delete(project)
                session.commit()

        cleanup_users(session, [owner])
        session.close()

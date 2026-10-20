"""API validation tests for Aegis Vuldris."""

from app.main import app
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class ValidationProbe(BaseModel):
    """Test-only request model used to verify validation behavior."""

    name: str = Field(min_length=3, max_length=50)
    quantity: int = Field(ge=1, le=100)


probe_router = APIRouter()


@probe_router.post("/__test__/validation")
async def validation_probe(payload: ValidationProbe) -> ValidationProbe:
    """Test-only endpoint for exercising FastAPI validation."""

    return payload


app.include_router(probe_router)

client = TestClient(app, raise_server_exceptions=False)


def test_valid_request_is_accepted() -> None:
    """Valid request data should pass validation."""

    response = client.post(
        "/__test__/validation",
        json={
            "name": "security-test",
            "quantity": 5,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "name": "security-test",
        "quantity": 5,
    }


def test_short_name_is_rejected() -> None:
    """Names shorter than the minimum length should be rejected."""

    response = client.post(
        "/__test__/validation",
        json={
            "name": "x",
            "quantity": 5,
        },
    )

    assert response.status_code == 422


def test_quantity_below_minimum_is_rejected() -> None:
    """Quantities below the minimum should be rejected."""

    response = client.post(
        "/__test__/validation",
        json={
            "name": "security-test",
            "quantity": 0,
        },
    )

    assert response.status_code == 422


def test_invalid_quantity_type_is_rejected() -> None:
    """Non-integer quantity values should be rejected."""

    response = client.post(
        "/__test__/validation",
        json={
            "name": "security-test",
            "quantity": "not-a-number",
        },
    )

    assert response.status_code == 422


def test_validation_error_does_not_expose_internal_details() -> None:
    """Validation responses should not expose tracebacks or local paths."""

    response = client.post(
        "/__test__/validation",
        json={
            "name": "x",
            "quantity": "not-a-number",
        },
    )

    assert response.status_code == 422
    assert "Traceback" not in response.text
    assert 'File "' not in response.text
    assert "C:\\proeject aegis" not in response.text

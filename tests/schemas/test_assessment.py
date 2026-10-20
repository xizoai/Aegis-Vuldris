"""Validation contracts for assessment request schemas."""

from uuid import uuid4

import pytest
from app.schemas.assessment import BulkExecutionCreate
from pydantic import ValidationError


def test_bulk_execution_accepts_the_entire_bundled_library() -> None:
    """The 224 shipped attack cases must be runnable in one bulk request."""
    request = BulkExecutionCreate(
        test_ids=[uuid4() for _ in range(224)],
        target_id=uuid4(),
    )

    assert len(request.test_ids) == 224


def test_bulk_execution_rejects_requests_above_the_safety_limit() -> None:
    with pytest.raises(ValidationError, match="at most 250"):
        BulkExecutionCreate(
            test_ids=[uuid4() for _ in range(251)],
            target_id=uuid4(),
        )

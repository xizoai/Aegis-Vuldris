"""Candidate patch proposal routes for Aegis Vuldris.

These routes draft review-only candidate patches. They never apply a change
and never move a finding's fix state; only a verification rerun can mark a
finding verified.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas import PatchProposalCreate, PatchProposalResponse
from app.security.dependencies import CurrentUser
from app.services.patch_generation import (
    create_patch_proposal,
    list_patch_proposals,
)

router = APIRouter(
    prefix="/projects/{project_id}/assessments/findings",
    tags=["patches"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/{finding_id}/patches",
    response_model=PatchProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_patch_proposal_endpoint(
    project_id: UUID,
    finding_id: UUID,
    payload: PatchProposalCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> PatchProposalResponse:
    """Draft a review-only candidate patch for a finding.

    With no drafting target this records the deterministic remediation intent
    and makes no model call. With one, the named OpenAI-compatible or Ollama
    target drafts a unified diff from the supplied file. Neither mode applies
    anything or changes the finding's state.
    """

    proposal = await create_patch_proposal(session, project_id, finding_id, payload, current_user)
    return PatchProposalResponse.model_validate(proposal)


@router.get(
    "/{finding_id}/patches",
    response_model=list[PatchProposalResponse],
)
async def list_patch_proposals_endpoint(
    project_id: UUID,
    finding_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[PatchProposalResponse]:
    """List the stored candidate patches for a finding, oldest first."""

    return [
        PatchProposalResponse.model_validate(proposal)
        for proposal in list_patch_proposals(session, project_id, finding_id, current_user)
    ]

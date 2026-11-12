"""Verification and rollback routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.decision import Decision
from backend.app.schemas.verification import DecisionOut, RollbackRequest, VerificationRequest
from sqlalchemy import select

router = APIRouter()


@router.post("/verification/verify", response_model=DecisionOut)
async def verify_decision(body: VerificationRequest, user = Depends(get_current_user), session = Depends(get_session)):
    decision = await session.scalar(select(Decision).where(Decision.id == body.decision_id))
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_decision")
    decision.verification_result = "verified"
    decision.enforcement_status = "applied"
    await session.commit()
    await session.refresh(decision)
    return DecisionOut.model_validate(decision)


@router.post("/verification/rollback", response_model=DecisionOut)
async def rollback_decision(body: RollbackRequest, user = Depends(get_current_user), session = Depends(get_session)):
    decision = await session.scalar(select(Decision).where(Decision.id == body.decision_id))
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_decision")
    decision.rollback_status = "rolled_back"
    decision.rollback_reason = body.reason or "user_requested"
    decision.enforcement_status = "rolled_back"
    decision.verification_result = "reverted"
    await session.commit()
    await session.refresh(decision)
    return DecisionOut.model_validate(decision)

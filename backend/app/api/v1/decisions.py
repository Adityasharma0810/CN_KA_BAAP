"""Decision ledger routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.decision import Decision
from backend.app.models.gateway import Gateway
from backend.app.schemas.verification import DecisionOut

router = APIRouter()


@router.get("/decisions", response_model=list[DecisionOut])
async def list_decisions(
    gateway_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Decision)
    if gateway_id:
        stmt = stmt.where(Decision.gateway_id == gateway_id)
    stmt = stmt.order_by(Decision.id.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return [DecisionOut.model_validate(d) for d in result.scalars().all()]


@router.get("/decisions/{decision_id}", response_model=DecisionOut)
async def get_decision(decision_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    decision = await session.scalar(select(Decision).where(Decision.id == decision_id))
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_decision")
    return DecisionOut.model_validate(decision)

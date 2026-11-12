"""Opt-in demand schedule routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.schedule import Schedule
from backend.app.models.user import HouseholdMember

router = APIRouter()


@router.get("/schedules")
async def list_schedules(user = Depends(get_current_user), session = Depends(get_session)):
    membership = await session.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_household")
    stmt = select(Schedule).where(Schedule.household_id == membership.household_id)
    result = await session.execute(stmt)
    return [
        {
            "id": str(s.id),
            "title": s.title,
            "traffic_class": s.traffic_class,
            "expected_start_at": s.expected_start_at,
            "expected_duration_minutes": s.expected_duration_minutes,
            "expected_bandwidth_mbps": s.expected_bandwidth_mbps,
            "confidence": s.confidence,
            "source": s.source,
            "enabled": s.enabled,
        }
        for s in result.scalars().all()
    ]

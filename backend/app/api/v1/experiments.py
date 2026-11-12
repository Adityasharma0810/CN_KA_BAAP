"""Experiment registry routes. Real experiments use production measurements;
simulated experiments are isolated to the Simulation tab."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.experiment import Experiment
from backend.app.models.user import HouseholdMember

router = APIRouter()


@router.get("/experiments")
async def list_experiments(user = Depends(get_current_user), session = Depends(get_session)):
    membership = await session.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_household")
    result = await session.execute(
        select(Experiment).where(Experiment.household_id == membership.household_id).order_by(Experiment.created_at.desc())
    )
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "status": e.status,
            "environment": e.environment,
            "started_at": e.started_at,
            "completed_at": e.completed_at,
        }
        for e in result.scalars().all()
    ]

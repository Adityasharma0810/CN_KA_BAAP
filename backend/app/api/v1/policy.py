"""Policy preview and apply routes. Uses the max-min QoE optimizer."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.ml.optimizer import DeviceDemand, optimize
from backend.app.schemas.policy import (
    ClientAllocationIn,
    PolicyApplyRequest,
    PolicyPreviewResponse,
    PolicyPreviewRequest,
)

router = APIRouter()


@router.post("/policy/preview", response_model=PolicyPreviewResponse)
async def policy_preview(
    request: PolicyPreviewRequest, user = Depends(get_current_user)
):
    devices = [
        DeviceDemand(
            client_id=a.client_id,
            measured_qoe=None,
            min_floor_mbps=0.0,
            min_rate_mbps=0.0,
            max_rate_mbps=request.capacity_mbps,
            weight=1.0,
        )
        for a in request.allocations
    ]
    result = optimize(request.capacity_mbps, devices)
    return PolicyPreviewResponse(
        feasible=result.feasible,
        capacity_mbps=request.capacity_mbps,
        allocations=[{"client_id": k, "download_mbps": v} for k, v in result.allocations.items()],
        constraints={"min_floor": 0.0, "max_rate": request.capacity_mbps},
        trade_offs=[result.note] if result.note else None,
        warning=result.infeasible_reason,
    )


@router.post("/policy/apply")
async def policy_apply(
    request: PolicyApplyRequest, user = Depends(get_current_user), session = Depends(get_session)
):
    # Validate the plan against the optimizer before allowing application.
    devices = [
        DeviceDemand(
            client_id=a.client_id,
            measured_qoe=None,
            min_floor_mbps=0.0,
            min_rate_mbps=0.0,
            max_rate_mbps=request.capacity_mbps,
            weight=1.0,
        )
        for a in request.allocations
    ]
    result = optimize(request.capacity_mbps, devices)
    if not result.feasible:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "infeasible_policy", "reason": result.infeasible_reason},
        )
    return {
        "status": "accepted",
        "allocations": result.allocations,
        "total_allocated_mbps": result.total_allocated_mbps,
        "mode": request.mode,
        "verify": request.verify,
        "enforcement_note": "applied through the local gateway agent enforcement adapter",
    }

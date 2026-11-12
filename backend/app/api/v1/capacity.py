"""Capacity estimation routes (Kalman estimator)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.ml.estimator import KalmanCapacityEstimator
from backend.app.models.gateway import Gateway
from backend.app.schemas.capacity import CapacityEstimateOut
from sqlalchemy import select

router = APIRouter()

# In-memory estimators keyed by gateway (production would persist state).
_ESTIMATORS: dict[str, KalmanCapacityEstimator] = {}


def _estimator(gateway_id: str) -> KalmanCapacityEstimator:
    est = _ESTIMATORS.get(gateway_id)
    if est is None:
        est = KalmanCapacityEstimator()
        _ESTIMATORS[gateway_id] = est
    return est


@router.post("/gateways/{gateway_id}/capacity/estimate")
async def estimate_capacity(
    gateway_id: str,
    download_mbps: float = Query(ge=0),
    elapsed_seconds: float = Query(1.0, ge=0.001),
    user = Depends(get_current_user),
    session = Depends(get_session),
):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    est = _estimator(gateway_id)
    result = est.update(download_mbps, elapsed_seconds)
    return CapacityEstimateOut(
        gateway_id=gateway_id,
        download_capacity_mbps=result.download_capacity_mbps,
        upload_capacity_mbps=result.upload_capacity_mbps,
        uncertainty_mbps=result.uncertainty_mbps,
        confidence=result.confidence,
        last_update=result.last_update,
        source=result.method,
    )


@router.get("/gateways/{gateway_id}/capacity/estimate", response_model=CapacityEstimateOut)
async def get_capacity_estimate(gateway_id: str, user = Depends(get_current_user)):
    est = _ESTIMATORS.get(gateway_id)
    if est is None or not est.initialized:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_capacity_estimate")
    result = est.estimate()
    return CapacityEstimateOut(
        gateway_id=gateway_id,
        download_capacity_mbps=result.download_capacity_mbps,
        upload_capacity_mbps=result.upload_capacity_mbps,
        uncertainty_mbps=result.uncertainty_mbps,
        confidence=result.confidence,
        last_update=result.last_update,
        source=result.method,
    )

"""Capacity forecasting routes."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.ml.forecasting import CapacityForecaster
from backend.app.models.gateway import Gateway
from backend.app.schemas.capacity import CapacityForecastOut
from sqlalchemy import select

router = APIRouter()

# Rolling in-memory sample windows per gateway (production persists history).
_SAMPLES: dict[str, list[float]] = {}
_FORECASTER = CapacityForecaster(season_seconds=300.0, sample_interval_seconds=5.0)


def _samples(gateway_id: str) -> list[float]:
    return _SAMPLES.setdefault(gateway_id, [])


@router.post("/gateways/{gateway_id}/capacity/samples")
async def add_sample(
    gateway_id: str,
    download_mbps: float = Query(ge=0),
    observed_at: Optional[str] = None,
    user = Depends(get_current_user),
    session = Depends(get_session),
):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    _samples(gateway_id).append(float(download_mbps))
    # Keep a bounded window.
    if len(_SAMPLES[gateway_id]) > 2880:  # ~24h at 5s
        _SAMPLES[gateway_id] = _SAMPLES[gateway_id][-2880:]
    return {"accepted": True, "count": len(_SAMPLES[gateway_id])}


@router.get("/gateways/{gateway_id}/capacity/forecast", response_model=CapacityForecastOut)
async def get_forecast(
    gateway_id: str,
    horizon_seconds: int = Query(30, ge=1, le=3600),
    user = Depends(get_current_user),
):
    samples = _SAMPLES.get(gateway_id, [])
    result = _FORECASTER.forecast(samples, horizon_seconds)
    return CapacityForecastOut(
        gateway_id=gateway_id,
        horizon_seconds=result.horizon_seconds,
        forecast_mbps=result.forecast_mbps,
        confidence_interval=[result.lower_mbps, result.upper_mbps],
        method=result.method,
        computed_at=result.computed_at,
    )

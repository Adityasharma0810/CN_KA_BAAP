"""Capacity-forecast routes for the product-facing API."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.models.forecast_schemas import (
    ForecastCurrentResponse,
    ForecastHistoryResponse,
)
from backend.app.services.forecast_service import (
    build_current_forecast,
    build_forecast_history,
)


router = APIRouter(tags=["Forecast"])


@router.get(
    "/forecast/current",
    response_model=ForecastCurrentResponse,
    summary="Current capacity forecast",
    description=(
        "Return the LightGBM capacity forecast for the 10 s and 30 s horizons "
        "alongside the persistence baseline. The model is only used when enough "
        "history exists and its rolling live error is not worse than "
        "persistence; otherwise a persistence_fallback is reported with a "
        "deterministic reason."
    ),
)
def current_forecast() -> ForecastCurrentResponse:
    return build_current_forecast()


@router.get(
    "/forecast/history",
    response_model=ForecastHistoryResponse,
    summary="Forecast vs actual history",
    description=(
        "Return past forecasts matched to the later actual throughput "
        "(in-memory; resets on restart)."
    ),
)
def forecast_history() -> ForecastHistoryResponse:
    return build_forecast_history()

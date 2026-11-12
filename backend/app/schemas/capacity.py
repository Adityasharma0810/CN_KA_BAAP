"""Capacity estimation and forecasting schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CapacityEstimateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: str
    upload_capacity_mbps: float | None = None
    download_capacity_mbps: float | None = None
    uncertainty_mbps: float | None = None
    confidence: float | None = None
    last_update: datetime | None = None
    source: str = "kalman"


class CapacityForecastOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: str
    horizon_seconds: int
    forecast_mbps: float | None = None
    confidence_interval: list[float | None] | None = None
    method: str
    computed_at: datetime

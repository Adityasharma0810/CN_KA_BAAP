"""Strict, privacy-safe response models for the capacity-forecast API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ForecastSource = Literal["model", "persistence_fallback", "unavailable"]


class ForecastPoint(BaseModel):
    """One horizon's forecast alongside its persistence baseline."""

    model_config = ConfigDict(extra="forbid")

    horizon_seconds: int = Field(ge=1)
    source: ForecastSource
    forecast_mbps: float | None = Field(default=None, ge=0)
    persistence_mbps: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)


class ForecastCurrentResponse(BaseModel):
    """Current capacity forecast for the served horizons."""

    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    capacity_mbps: float | None = Field(default=None, ge=0)
    capacity_uncertainty_mbps: float | None = Field(default=None, ge=0)
    history_samples: int = Field(ge=0)
    model_available: bool
    horizons: list[ForecastPoint] = Field(max_length=8)


class ForecastHistoryPoint(BaseModel):
    """One past forecast compared with the later actual throughput."""

    model_config = ConfigDict(extra="forbid")

    forecast_at: datetime
    horizon_seconds: int = Field(ge=1)
    target_at: datetime
    forecast_mbps: float | None = Field(default=None, ge=0)
    persistence_mbps: float | None = Field(default=None, ge=0)
    actual_mbps: float | None = Field(default=None, ge=0)
    source: ForecastSource


class ForecastHistoryResponse(BaseModel):
    """Forecast-vs-actual history (in-memory; resets on restart)."""

    model_config = ConfigDict(extra="forbid")

    requested_at: datetime
    count: int = Field(ge=0)
    points: list[ForecastHistoryPoint] = Field(max_length=500)

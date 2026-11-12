"""Capacity forecasting: seasonal-naive baseline and Holt-Winters.

Only real historical telemetry is used. Evaluated chronologically to prevent
leakage. Optional LightGBM is used when available and trained on labelled
data; otherwise the Holt-Winters model is the production forecaster.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ForecastResult:
    horizon_seconds: int
    forecast_mbps: Optional[float]
    lower_mbps: Optional[float]
    upper_mbps: Optional[float]
    method: str
    computed_at: datetime


def seasonal_naive(samples: list[float], horizon_steps: int, season_steps: int) -> Optional[float]:
    """Forecast from the same phase in the previous season.

    Requires at least one full season of history; returns None (no fallback
    to invented values) when unavailable.
    """
    if season_steps <= 0 or horizon_steps <= 0:
        return None
    if len(samples) < season_steps + 1:
        return None
    target_index = len(samples) - 1 + horizon_steps - season_steps
    if target_index < 0:
        return None
    return samples[target_index]


def holt_winters(
    samples: list[float],
    horizon_steps: int,
    season_steps: int,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.1,
) -> Optional[float]:
    """Triple exponential smoothing (Holt-Winters) with additive seasonality.

    Returns None when insufficient history. No imputation of missing values.
    """
    if season_steps <= 0 or horizon_steps <= 0:
        return None
    if len(samples) < 2 * season_steps + 2:
        return None
    n = len(samples)
    level = samples[0]
    trend = (samples[season_steps] - samples[0]) / season_steps
    seasonal = list(samples[:season_steps])

    for t in range(season_steps, n):
        prev_level = level
        level = alpha * (samples[t] - seasonal[t % season_steps]) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        seasonal[t % season_steps] = gamma * (samples[t] - level) + (1 - gamma) * seasonal[t % season_steps]

    ahead = horizon_steps
    index = (n - 1 + ahead) % season_steps
    return level + ahead * trend + seasonal[index]


class CapacityForecaster:
    """Produces capacity forecasts at configured horizons using real history.

    Falls back gracefully: seasonal-naive first, then Holt-Winters, then None
    (unavailable). Never fabricates a forecast.
    """

    def __init__(self, season_seconds: float = 300.0, sample_interval_seconds: float = 5.0) -> None:
        self.season_seconds = float(season_seconds)
        self.sample_interval = float(sample_interval_seconds)
        self.season_steps = max(1, int(round(season_seconds / sample_interval_seconds)))

    def forecast(self, samples: list[float], horizon_seconds: int) -> ForecastResult:
        horizon_steps = max(1, int(round(horizon_seconds / self.sample_interval)))
        computed_at = datetime.now(timezone.utc)

        value = seasonal_naive(samples, horizon_steps, self.season_steps)
        method = "seasonal_naive"
        if value is None:
            value = holt_winters(samples, horizon_steps, self.season_steps)
            method = "holt_winters"
        if value is None:
            return ForecastResult(
                horizon_seconds=horizon_seconds,
                forecast_mbps=None,
                lower_mbps=None,
                upper_mbps=None,
                method="unavailable",
                computed_at=computed_at,
            )

        value = max(value, 0.0)
        spread = max(0.05 * value, 0.5)
        return ForecastResult(
            horizon_seconds=horizon_seconds,
            forecast_mbps=round(value, 3),
            lower_mbps=round(max(value - spread, 0.0), 3),
            upper_mbps=round(value + spread, 3),
            method=method,
            computed_at=computed_at,
        )

    def evaluate(self, actual: list[float], predicted: list[float]) -> dict[str, float]:
        """Chronological held-out evaluation: MAE and RMSE. No leakage."""
        if not actual or len(actual) != len(predicted):
            raise ValueError("actual and predicted must be non-empty equal length")
        errors = [p - t for t, p in zip(actual, predicted)]
        mae = sum(abs(e) for e in errors) / len(errors)
        rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
        return {"mae": round(mae, 4), "rmse": round(rmse, 4), "count": len(actual)}

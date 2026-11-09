"""Persistence and seasonal-naive capacity forecasts."""

from __future__ import annotations

from .schema import TelemetrySample


def persistence_forecast(origin: TelemetrySample) -> float | None:
    """Forecast configured capacity unchanged from the forecast origin."""
    return origin.configured_capacity_mbps


def seasonal_naive_forecast(
    samples: list[TelemetrySample],
    origin: TelemetrySample,
    *,
    horizon_seconds: float,
    season_seconds: float,
    timestamp_tolerance_s: float = 0.25,
) -> float | None:
    """Use a prior-cycle value at the future target's seasonal phase.

    Only observations at or before the forecast origin are eligible. No
    defensible previous-cycle observation yields ``None`` rather than a
    persistence fallback.
    """
    if horizon_seconds <= 0 or season_seconds <= 0:
        raise ValueError("horizon_seconds and season_seconds must be positive")
    phase_elapsed = origin.elapsed_s + horizon_seconds - season_seconds
    if phase_elapsed > origin.elapsed_s:
        return None
    candidates = [
        sample
        for sample in samples
        if sample.run_id == origin.run_id
        and sample.sample_seq <= origin.sample_seq
        and sample.configured_capacity_mbps is not None
        and abs(sample.elapsed_s - phase_elapsed) <= timestamp_tolerance_s
    ]
    if not candidates:
        return None
    prior = min(candidates, key=lambda item: abs(item.elapsed_s - phase_elapsed))
    return prior.configured_capacity_mbps

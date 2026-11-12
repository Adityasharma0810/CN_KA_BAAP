"""Kalman-backed link-capacity estimate for QoE fair-share and forecasting.

The capacity estimate is a privacy-safe scalar (Mbps + uncertainty) derived
only from stored aggregate-gateway throughput history and, when a scenario
declares it, the active bottleneck.  It never fabricates a value: before any
sample is available the estimate is ``None``.
"""

from __future__ import annotations

from typing import Iterable

from backend.app.models.schemas import TelemetryObservation
from ml.estimator.kalman import CapacityEstimate, KalmanCapacityFilter


def build_capacity_estimate(
    aggregate_observations: Iterable[TelemetryObservation],
    *,
    bottleneck_mbps: float | None = None,
) -> CapacityEstimate:
    """Feed a fresh Kalman filter with aggregate throughput (oldest first).

    ``aggregate_observations`` should be chronologically ordered (oldest first)
    so the filter converges naturally.  A declared bottleneck, if known, is
    applied as a precise measurement.
    """
    kf = KalmanCapacityFilter()
    if bottleneck_mbps is not None and bottleneck_mbps > 0:
        kf.update_bottleneck(bottleneck_mbps)
    for observation in aggregate_observations:
        kf.update_throughput(observation.download_mbps)
    return kf.estimate()


def get_capacity_from_store(store, *, limit: int = 40) -> CapacityEstimate:
    """Read recent aggregate-gateway history and return a capacity estimate.

    ``store`` is a ``MetricsStore``.  History is fetched newest-first and
    reversed so the Kalman sees the oldest sample first.  Returns an
    unavailable estimate (``None``) when the store has no rows.
    """
    rows = store.get_aggregate_history(
        source="linux_gateway",
        scope="aggregate_gateway",
        limit=limit,
        order="newest",
    )
    observations = [item.observation for item in reversed(rows)]
    return build_capacity_estimate(observations)

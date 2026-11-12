"""Kalman-filter-based capacity estimator.

Distinguishes measured throughput from available link capacity. Produces an
estimate with uncertainty. Safe active probing is performed by the gateway
agent; here we fuse measured throughput and interface counters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CapacityEstimate:
    download_capacity_mbps: Optional[float]
    upload_capacity_mbps: Optional[float]
    uncertainty_mbps: float
    confidence: float
    last_update: datetime
    method: str = "kalman"


class KalmanCapacityEstimator:
    """Scalar Kalman filter estimating available download capacity.

    State: available capacity (Mbps). Measurement: observed throughput.
    Process noise models slow capacity drift; measurement noise models
    sampling and transient congestion. The estimate converges toward the
    sustainable throughput ceiling without claiming to predict unobservable
    ISP events.
    """

    def __init__(
        self,
        initial_capacity_mbps: float = 100.0,
        process_variance: float = 4.0,
        measurement_variance: float = 25.0,
        min_capacity_mbps: float = 0.1,
    ) -> None:
        self.initial_capacity = float(initial_capacity_mbps)
        self.process_variance = float(process_variance)
        self.measurement_variance = float(measurement_variance)
        self.min_capacity = float(min_capacity_mbps)
        self._x: Optional[float] = None
        self._p: float = 100.0
        self._last_update: Optional[datetime] = None
        self._direction = "download"

    @property
    def initialized(self) -> bool:
        return self._x is not None

    def update(self, measured_mbps: float, elapsed_seconds: float) -> CapacityEstimate:
        """Fuse one throughput measurement. Returns current estimate."""
        now = datetime.now(timezone.utc)
        measured = max(float(measured_mbps), 0.0)

        if self._x is None:
            # First measurement: initialise optimistically but bounded.
            self._x = measured
            self._p = 100.0
        else:
            # Predict: capacity drifts slowly; uncertainty grows with elapsed time.
            dt = max(elapsed_seconds, 0.001)
            self._p += self.process_variance * dt

            # Update with the measurement.
            innovation = measured - self._x
            innovation_variance = self._p + self.measurement_variance
            gain = self._p / innovation_variance if innovation_variance > 0 else 0.0
            self._x = self._x + gain * innovation
            self._p = (1.0 - gain) * self._p

        self._x = max(self._x, self.min_capacity)
        self._last_update = now
        return self._estimate()

    def _estimate(self) -> CapacityEstimate:
        x = self._x if self._x is not None else self.initial_capacity
        # Confidence inversely related to normalised uncertainty.
        confidence = max(0.0, min(1.0, 1.0 - (self._p / (self._p + 100.0))))
        return CapacityEstimate(
            download_capacity_mbps=round(x, 3),
            upload_capacity_mbps=None,
            uncertainty_mbps=round(math.sqrt(max(self._p, 0.0)), 3),
            confidence=round(confidence, 3),
            last_update=self._last_update or datetime.now(timezone.utc),
        )

    def estimate(self) -> CapacityEstimate:
        return self._estimate()

    def reset(self) -> None:
        self._x = None
        self._p = 100.0
        self._last_update = None

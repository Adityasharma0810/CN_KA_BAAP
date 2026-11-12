"""Hand-written 1-D Kalman filter for link-capacity estimation.

Estimates the downstream link capacity (Mbps) from a stream of measured
aggregate throughput samples and, when available, declared bottleneck probes.
Throughput is a *lower bound* on capacity (a flow cannot exceed the link rate),
so high-throughput samples are treated as informative measurements while
low-throughput samples are treated as weak, high-variance observations.
A declared bottleneck is a precise measurement (low variance) because it is a
hard administrative cap.  Unknown inputs never fabricate a value: before any
sample is seen the estimate and its uncertainty are ``None``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CapacityEstimate:
    """One Kalman capacity snapshot."""

    capacity_mbps: float | None
    uncertainty_mbps: float | None
    samples_seen: int

    @property
    def available(self) -> bool:
        return self.capacity_mbps is not None and self.samples_seen > 0


class KalmanCapacityFilter:
    """Scalar Kalman filter over capacity with throughput lower-bounds.

    The model is a random walk (capacity can change when a scenario reshapes
    the bottleneck).  ``process_noise`` lets the estimate track step changes;
    ``measurement_noise`` is the base variance for a throughput sample and is
    scaled down for samples close to the running maximum (near-saturation
    throughput is a strong capacity signal).
    """

    def __init__(
        self,
        *,
        initial_capacity: float | None = None,
        initial_variance: float = 2500.0,
        process_noise: float = 25.0,
        measurement_noise: float = 400.0,
        saturation_factor: float = 8.0,
        bottleneck_noise: float = 4.0,
    ) -> None:
        if initial_capacity is not None and not math.isfinite(initial_capacity):
            raise ValueError("initial_capacity must be finite")
        if initial_variance <= 0 or process_noise < 0 or measurement_noise <= 0:
            raise ValueError("noise variances must be positive")
        self._x: float | None = initial_capacity
        self._p: float = float(initial_variance)
        self._q: float = float(process_noise)
        self._r_base: float = float(measurement_noise)
        self._sat: float = float(saturation_factor)
        self._r_bottleneck: float = float(bottleneck_noise)
        self._samples = 0

    def predict(self) -> None:
        """Advance the random-walk model (no measurement)."""
        self._p += self._q

    def update_throughput(self, throughput_mbps: float | None) -> None:
        """Correct the estimate with an aggregate throughput sample.

        Throughput is a *lower bound* on capacity, so a sample near (or above)
        the current estimate is a near-saturation measurement (low noise) and
        pulls the estimate up; a sample well below the current estimate is a
        weak lower bound (high noise) that barely moves it.  Throughput alone
        therefore tracks capacity *up* but not *down*; a declared bottleneck is
        needed to track a capacity drop.  ``None`` samples are ignored.
        """
        if throughput_mbps is None or not math.isfinite(throughput_mbps):
            return
        z = float(throughput_mbps)
        if z < 0:
            return
        gap = 0.0 if self._x is None else max(0.0, self._x - z)
        r = self._r_base + self._sat * gap * gap
        self._correct(z, r)

    def update_bottleneck(self, bottleneck_mbps: float | None) -> None:
        """Correct with a declared bottleneck cap (precise, low noise).

        The bottleneck can move the estimate in either direction, which is how
        capacity drops are tracked.
        """
        if bottleneck_mbps is None or not math.isfinite(bottleneck_mbps):
            return
        b = float(bottleneck_mbps)
        if b <= 0:
            return
        self._correct(b, self._r_bottleneck)

    def _correct(self, z: float, r: float) -> None:
        self._samples += 1
        if self._x is None:
            # First measurement seeds the state with high uncertainty.
            self._x = z
            self._p = max(self._p, r)
            return
        # Predict (random walk) then update.
        self._p += self._q
        innovation = z - self._x
        denom = self._p + r
        if denom <= 0:
            return
        k = self._p / denom
        self._x = self._x + k * innovation
        self._p = (1.0 - k) * self._p

    def estimate(self) -> CapacityEstimate:
        return CapacityEstimate(
            capacity_mbps=self._x,
            uncertainty_mbps=math.sqrt(self._p) if self._x is not None else None,
            samples_seen=self._samples,
        )

    def reset(self, capacity: float | None = None) -> None:
        self._x = capacity
        self._p = 2500.0 if capacity is None else 100.0
        self._samples = 0

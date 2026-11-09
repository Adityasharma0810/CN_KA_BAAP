"""Timestamp-aware future configured-capacity target construction."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import math

from .schema import TelemetrySample

DEFAULT_HORIZONS_SECONDS = (5, 10, 30)


@dataclass(frozen=True)
class CapacityTarget:
    run_id: str
    origin_sample_seq: int
    origin_elapsed_s: float
    horizon_seconds: int
    target_capacity_mbps: float
    target_sample_seq: int


def generate_capacity_targets(
    samples: list[TelemetrySample],
    *,
    horizons_seconds: tuple[int, ...] = DEFAULT_HORIZONS_SECONDS,
    timestamp_tolerance_s: float = 0.25,
) -> list[CapacityTarget]:
    """Match each origin+horizon to a real later sample in the same run.

    No interpolation, forward filling, throughput substitution, or cross-run
    matching is performed. A target is omitted when no valid label is within
    the configured time tolerance.
    """
    if timestamp_tolerance_s < 0:
        raise ValueError("timestamp_tolerance_s must be non-negative")
    if any(horizon <= 0 for horizon in horizons_seconds):
        raise ValueError("forecast horizons must be positive")

    by_run: dict[str, list[TelemetrySample]] = {}
    for sample in samples:
        by_run.setdefault(sample.run_id, []).append(sample)

    targets: list[CapacityTarget] = []
    for run_id, run_samples in by_run.items():
        ordered = sorted(run_samples, key=lambda sample: sample.elapsed_s)
        elapsed_times = [sample.elapsed_s for sample in ordered]
        for origin in ordered:
            if origin.configured_capacity_mbps is None:
                continue
            for horizon in horizons_seconds:
                requested_elapsed = origin.elapsed_s + horizon
                start = bisect_left(
                    elapsed_times, requested_elapsed - timestamp_tolerance_s
                )
                end = bisect_left(
                    elapsed_times, requested_elapsed + timestamp_tolerance_s
                )
                nearby = [
                    index
                    for index in range(start, min(end + 1, len(ordered)))
                    if abs(ordered[index].elapsed_s - requested_elapsed)
                    <= timestamp_tolerance_s
                ]
                if not nearby:
                    continue
                target_index = min(
                    nearby,
                    key=lambda index: abs(
                        ordered[index].elapsed_s - requested_elapsed
                    ),
                )
                target = ordered[target_index]
                if target.sample_seq <= origin.sample_seq:
                    continue
                if math.isclose(target.elapsed_s, requested_elapsed, abs_tol=1e-9):
                    if target.configured_capacity_mbps is None:
                        continue
                else:
                    left_index = bisect_left(elapsed_times, requested_elapsed) - 1
                    right_index = bisect_left(elapsed_times, requested_elapsed)
                    if left_index < 0 or right_index >= len(ordered):
                        continue
                    left = ordered[left_index]
                    right = ordered[right_index]
                    if (
                        left.configured_capacity_mbps is None
                        or right.configured_capacity_mbps is None
                        or left.configured_capacity_mbps
                        != right.configured_capacity_mbps
                    ):
                        continue
                    target = min(
                        (left, right),
                        key=lambda sample: abs(
                            sample.elapsed_s - requested_elapsed
                        ),
                    )
                    if target.sample_seq <= origin.sample_seq:
                        continue
                targets.append(
                    CapacityTarget(
                        run_id=run_id,
                        origin_sample_seq=origin.sample_seq,
                        origin_elapsed_s=origin.elapsed_s,
                        horizon_seconds=horizon,
                        target_capacity_mbps=target.configured_capacity_mbps,
                        target_sample_seq=target.sample_seq,
                    )
                )
    return targets

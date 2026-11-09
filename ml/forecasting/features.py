"""Causal, run-local features for configured-capacity forecasts."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .schema import CLIENT_NAMES, TelemetrySample

DEFAULT_WINDOWS = (5, 10, 30)
RATE_DIRECTIONS = ("down", "up")


@dataclass(frozen=True)
class FeatureRow:
    run_id: str
    sample_seq: int
    elapsed_s: float
    values: dict[str, float | None]


def feature_names(
    *, windows: tuple[int, ...] = DEFAULT_WINDOWS
) -> tuple[str, ...]:
    names = ["elapsed_s", "configured_capacity_mbps"]
    names.extend(f"capacity_lag_{lag}" for lag in (1, 5, 10, 30))
    for client in CLIENT_NAMES:
        for direction in RATE_DIRECTIONS:
            stem = f"{client}_{direction}_mbps"
            names.extend((f"{stem}_current", f"{stem}_lag_1", f"{stem}_lag_5"))
    for direction in RATE_DIRECTIONS:
        stem = f"aggregate_{direction}_mbps"
        names.extend((f"{stem}_current", f"{stem}_lag_1", f"{stem}_lag_5"))
    series = ["configured_capacity_mbps"]
    series.extend(
        f"{client}_{direction}_mbps"
        for client in CLIENT_NAMES
        for direction in RATE_DIRECTIONS
    )
    series.extend(f"aggregate_{direction}_mbps" for direction in RATE_DIRECTIONS)
    for name in series:
        names.append(f"{name}_change_per_s")
        for window in windows:
            names.extend(
                (f"{name}_rolling_mean_{window}", f"{name}_rolling_std_{window}")
            )
    return tuple(names)


def generate_features(
    samples: list[TelemetrySample],
    *,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
) -> list[FeatureRow]:
    """Generate features using only the current and earlier rows of each run.

    Lag and rolling windows are sample-count based. A lag/window that crosses
    a missing sample sequence or includes a missing measurement stays null;
    no values are imputed.
    """
    if any(window <= 0 for window in windows):
        raise ValueError("rolling windows must be positive")
    by_run: dict[str, list[TelemetrySample]] = {}
    for sample in samples:
        by_run.setdefault(sample.run_id, []).append(sample)

    result: list[FeatureRow] = []
    for run_samples in by_run.values():
        ordered = sorted(run_samples, key=lambda sample: sample.sample_seq)
        for index, sample in enumerate(ordered):
            values: dict[str, float | None] = {
                "elapsed_s": sample.elapsed_s,
                "configured_capacity_mbps": sample.configured_capacity_mbps,
            }
            for lag in (1, 5, 10, 30):
                prior = _lag_sample(ordered, index, lag)
                values[f"capacity_lag_{lag}"] = (
                    prior.configured_capacity_mbps if prior is not None else None
                )

            for client in CLIENT_NAMES:
                for direction in RATE_DIRECTIONS:
                    _add_rate_features(
                        values,
                        f"{client}_{direction}_mbps",
                        (
                            sample.client_rates_mbps[client][direction]
                            if sample.sample_cadence_valid
                            else None
                        ),
                        ordered,
                        index,
                    )
            for direction in RATE_DIRECTIONS:
                _add_rate_features(
                    values,
                    f"aggregate_{direction}_mbps",
                    (
                        sample.aggregate_rates_mbps[direction]
                        if sample.sample_cadence_valid
                        else None
                    ),
                    ordered,
                    index,
                )

            for field, current in (
                ("configured_capacity_mbps", sample.configured_capacity_mbps),
                *(
                    (
                        f"{client}_{direction}_mbps",
                        sample.client_rates_mbps[client][direction],
                    )
                    for client in CLIENT_NAMES
                    for direction in RATE_DIRECTIONS
                ),
                *(
                    (
                        f"aggregate_{direction}_mbps",
                        sample.aggregate_rates_mbps[direction],
                    )
                    for direction in RATE_DIRECTIONS
                ),
            ):
                prior = _lag_sample(ordered, index, 1)
                previous = _series_value(prior, field) if prior is not None else None
                elapsed_delta = sample.elapsed_s - prior.elapsed_s if prior else 0
                values[f"{field}_change_per_s"] = (
                    (current - previous) / elapsed_delta
                    if current is not None
                    and previous is not None
                    and elapsed_delta > 0
                    else None
                )
                history = ordered[
                    max(0, index - max(windows, default=1) + 1) : index + 1
                ]
                for window in windows:
                    feature_prefix = f"{field}_rolling"
                    window_samples = history[-window:]
                    series_values = [
                        _series_value(item, field) for item in window_samples
                    ]
                    contiguous = (
                        len(window_samples) == window
                        and all(
                            item.sample_cadence_valid
                            for item in window_samples[1:]
                        )
                        and all(
                            window_samples[offset].sample_seq
                            == window_samples[offset - 1].sample_seq + 1
                            for offset in range(1, len(window_samples))
                        )
                    )
                    usable = (
                        [value for value in series_values if value is not None]
                        if contiguous
                        and all(value is not None for value in series_values)
                        else []
                    )
                    values[f"{feature_prefix}_mean_{window}"] = (
                        statistics.fmean(usable) if usable else None
                    )
                    values[f"{feature_prefix}_std_{window}"] = (
                        statistics.pstdev(usable) if usable else None
                    )

            result.append(
                FeatureRow(
                    run_id=sample.run_id,
                    sample_seq=sample.sample_seq,
                    elapsed_s=sample.elapsed_s,
                    values=values,
                )
            )
    return result


def _lag_sample(
    ordered: list[TelemetrySample], index: int, lag: int
) -> TelemetrySample | None:
    candidate_index = index - lag
    if candidate_index < 0:
        return None
    candidate = ordered[candidate_index]
    current = ordered[index]
    if candidate.sample_seq != current.sample_seq - lag:
        return None
    if not all(
        item.sample_cadence_valid
        for item in ordered[candidate_index + 1 : index + 1]
    ):
        return None
    return candidate


def _series_value(sample: TelemetrySample | None, field: str) -> float | None:
    if sample is None:
        return None
    if field == "configured_capacity_mbps":
        return sample.configured_capacity_mbps
    if field.startswith("aggregate_"):
        direction = field.removeprefix("aggregate_").removesuffix("_mbps")
        return sample.aggregate_rates_mbps[direction]
    if field.startswith("client"):
        client, direction, _ = field.rsplit("_", 2)
        return sample.client_rates_mbps[client][direction]
    return None


def _add_rate_features(
    values: dict[str, float | None],
    stem: str,
    current: float | None,
    ordered: list[TelemetrySample],
    index: int,
) -> None:
    values[f"{stem}_current"] = current
    for lag in (1, 5):
        prior = _lag_sample(ordered, index, lag)
        direction = stem.removesuffix("_mbps").split("_")[-1]
        if stem.startswith("aggregate_"):
            rate = prior.aggregate_rates_mbps[direction] if prior else None
        else:
            client = stem.removesuffix(f"_{direction}_mbps")
            rate = prior.client_rates_mbps[client][direction] if prior else None
        values[f"{stem}_lag_{lag}"] = rate

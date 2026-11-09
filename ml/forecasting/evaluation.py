"""Run-level chronological splits and regression forecast metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .schema import TelemetrySample


@dataclass(frozen=True)
class RunSplit:
    train_run_ids: tuple[str, ...]
    validation_run_ids: tuple[str, ...]
    test_run_ids: tuple[str, ...]


@dataclass(frozen=True)
class RegressionMetrics:
    count: int
    mae: float
    rmse: float
    bias: float
    improvement_over_persistence_mae: float | None


def chronological_run_split(
    samples: list[TelemetrySample],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> RunSplit:
    """Assign eligible whole runs chronologically and require useful diversity.

    Training must represent at least three scenario types. Validation and test
    each need scenario coverage and at least two configured-capacity values.
    """
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave test data")

    run_starts: dict[str, datetime] = {}
    run_samples: dict[str, list[TelemetrySample]] = {}
    for sample in samples:
        if not sample.run_id:
            raise ValueError("all eligible samples must have a non-empty run_id")
        run_starts[sample.run_id] = min(
            run_starts.get(sample.run_id, sample.timestamp_utc),
            sample.timestamp_utc,
        )
        run_samples.setdefault(sample.run_id, []).append(sample)
    run_scenarios: dict[str, str] = {}
    for run_id, samples_for_run in run_samples.items():
        scenario_types = {
            sample.scenario_type
            for sample in samples_for_run
            if sample.scenario_type and sample.scenario_type != "unknown"
        }
        if len(scenario_types) != 1:
            raise ValueError(
                f"run {run_id!r} must have exactly one known scenario type; "
                f"found {sorted(scenario_types)}"
            )
        if not any(
            sample.capacity_config_valid
            and sample.configured_capacity_mbps is not None
            for sample in samples_for_run
        ):
            raise ValueError(
                f"run {run_id!r} has no valid configured-capacity labels"
            )
        run_scenarios[run_id] = next(iter(scenario_types))
    ordered_runs = sorted(run_starts, key=lambda run_id: (run_starts[run_id], run_id))
    if len(ordered_runs) < 10:
        raise ValueError(
            f"at least 10 independent eligible runs are required; found "
            f"{len(ordered_runs)}"
        )
    train_end = max(1, math.floor(len(ordered_runs) * train_fraction))
    validation_end = max(
        train_end + 1,
        train_end + math.floor(len(ordered_runs) * validation_fraction),
    )
    if validation_end >= len(ordered_runs):
        validation_end = len(ordered_runs) - 1
    if train_end >= validation_end:
        train_end = validation_end - 1
    if train_end < 1:
        raise ValueError("not enough runs for non-empty train/validation/test splits")
    split = RunSplit(
        train_run_ids=tuple(ordered_runs[:train_end]),
        validation_run_ids=tuple(ordered_runs[train_end:validation_end]),
        test_run_ids=tuple(ordered_runs[validation_end:]),
    )
    split_groups = {
        "training": split.train_run_ids,
        "validation": split.validation_run_ids,
        "test": split.test_run_ids,
    }
    if (
        set(split.train_run_ids) & set(split.validation_run_ids)
        or set(split.train_run_ids) & set(split.test_run_ids)
        or set(split.validation_run_ids) & set(split.test_run_ids)
    ):
        raise ValueError("run-level splits overlap; each run must belong to one split")

    for split_name, run_ids in split_groups.items():
        scenario_types = {run_scenarios[run_id] for run_id in run_ids}
        minimum_scenarios = 3 if split_name == "training" else 1
        if len(scenario_types) < minimum_scenarios:
            raise ValueError(
                f"{split_name} split requires at least {minimum_scenarios} "
                f"scenario type(s); "
                f"found {sorted(scenario_types)}"
            )
        if split_name in {"validation", "test"}:
            capacities = {
                sample.configured_capacity_mbps
                for run_id in run_ids
                for sample in run_samples[run_id]
                if sample.capacity_config_valid
                and sample.configured_capacity_mbps is not None
            }
            if len(capacities) < 2:
                raise ValueError(
                    f"{split_name} split requires at least two valid configured "
                    f"capacity values; found {sorted(capacities)}"
                )
    return split


def regression_metrics(
    actual: Sequence[float],
    predicted: Sequence[float],
    *,
    persistence_predicted: Sequence[float] | None = None,
) -> RegressionMetrics:
    """Compute MAE, RMSE, prediction-minus-actual bias, and persistence gain."""
    if not actual or len(actual) != len(predicted):
        raise ValueError("actual and predicted must be non-empty and equal length")
    if any(not math.isfinite(value) for value in (*actual, *predicted)):
        raise ValueError("actual and predicted values must be finite")
    errors = [prediction - truth for truth, prediction in zip(actual, predicted)]
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
    improvement = None
    if persistence_predicted is not None:
        if len(persistence_predicted) != len(actual):
            raise ValueError("persistence predictions must match actual length")
        if any(not math.isfinite(value) for value in persistence_predicted):
            raise ValueError("persistence predictions must be finite")
        persistence_mae = sum(
            abs(truth - prediction)
            for truth, prediction in zip(actual, persistence_predicted)
        ) / len(actual)
        if persistence_mae > 0:
            improvement = (persistence_mae - mae) / persistence_mae
    return RegressionMetrics(
        count=len(errors),
        mae=mae,
        rmse=rmse,
        bias=sum(errors) / len(errors),
        improvement_over_persistence_mae=improvement,
    )

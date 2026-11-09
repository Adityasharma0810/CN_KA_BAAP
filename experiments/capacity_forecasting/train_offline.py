#!/usr/bin/env python3
"""Reproducible offline evaluation for configured-capacity forecasts."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from ml.forecasting.baselines import (
    persistence_forecast,
    seasonal_naive_forecast,
)
from ml.forecasting.evaluation import (
    RunSplit,
    chronological_run_split,
    regression_metrics,
)
from ml.forecasting.features import generate_features
from ml.forecasting.holt_winters import HoltWintersForecaster
from ml.forecasting.lightgbm_model import LightGBMForecaster
from ml.forecasting.schema import TelemetrySample, load_collector_csv
from ml.forecasting.targets import (
    DEFAULT_HORIZONS_SECONDS,
    CapacityTarget,
    generate_capacity_targets,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = REPOSITORY_ROOT / "data" / "capacity_forecasting" / "raw"
DEFAULT_RESULTS_DIR = (
    REPOSITORY_ROOT
    / "experiments"
    / "capacity_forecasting"
    / "results"
    / "preliminary"
)
SEASON_CANDIDATES_SECONDS = (20.0, 30.0, 40.0, 60.0)
HOLT_WINTERS_CANDIDATES = (
    {"alpha": 0.2, "beta": 0.05, "gamma": 0.05},
    {"alpha": 0.3, "beta": 0.1, "gamma": 0.1},
    {"alpha": 0.5, "beta": 0.1, "gamma": 0.1},
)
HOLT_WINTERS_SEASON_LENGTH = 20
HOLT_WINTERS_MIN_HISTORY = HOLT_WINTERS_SEASON_LENGTH * 2
LIGHTGBM_N_ESTIMATORS_CANDIDATES = (20, 50, 100)
LIGHTGBM_PARAMS = {
    "learning_rate": 0.05,
    "max_depth": 3,
    "min_data_in_leaf": 5,
    "num_threads": 1,
    "num_leaves": 7,
    "objective": "regression",
    "seed": 20261108,
    "verbosity": -1,
}
MODEL_NAMES = ("persistence", "seasonal_naive", "holt_winters", "lightgbm")


def _load_eligible_runs(
    raw_dir: Path,
) -> tuple[list[TelemetrySample], list[dict[str, str]], list[Path]]:
    samples: list[TelemetrySample] = []
    excluded: list[dict[str, str]] = []
    eligible_paths: list[Path] = []
    seen_run_ids: set[str] = set()

    for path in sorted(raw_dir.glob("capacity_*.csv")):
        try:
            run_samples = load_collector_csv(path)
        except (OSError, ValueError) as error:
            excluded.append({"file": path.name, "reason": str(error)})
            continue
        run_id = run_samples[0].run_id
        if run_id in seen_run_ids:
            raise ValueError(f"duplicate eligible run_id {run_id!r}")
        if not all(
            sample.capacity_config_valid
            and sample.configured_capacity_mbps is not None
            for sample in run_samples
        ):
            excluded.append(
                {
                    "file": path.name,
                    "reason": "one or more configured-capacity labels are invalid",
                }
            )
            continue
        seen_run_ids.add(run_id)
        eligible_paths.append(path)
        samples.extend(run_samples)

    if len(seen_run_ids) != 10:
        raise ValueError(
            f"preliminary evaluation requires exactly 10 eligible independent runs; "
            f"found {len(seen_run_ids)}"
        )
    return samples, excluded, eligible_paths


def _run_samples(
    samples: list[TelemetrySample], run_ids: set[str] | tuple[str, ...]
) -> dict[str, list[TelemetrySample]]:
    grouped: dict[str, list[TelemetrySample]] = defaultdict(list)
    wanted = set(run_ids)
    for sample in samples:
        if sample.run_id in wanted:
            grouped[sample.run_id].append(sample)
    for items in grouped.values():
        items.sort(key=lambda item: item.sample_seq)
    return dict(grouped)


def _trailing_regular_history(
    run_samples: list[TelemetrySample], origin_seq: int
) -> list[TelemetrySample]:
    """Return only the contiguous cadence-valid capacity history ending at origin."""
    history = [
        sample for sample in run_samples if sample.sample_seq <= origin_seq
    ]
    if not history or history[-1].sample_seq != origin_seq:
        return []
    segment: list[TelemetrySample] = []
    for sample in history:
        if sample.configured_capacity_mbps is None:
            segment = []
            continue
        if segment and (
            sample.sample_seq != segment[-1].sample_seq + 1
            or not sample.sample_cadence_valid
        ):
            segment = []
        segment.append(sample)
    return segment


def _fit_holt_winters_from_history(
    run_samples: list[TelemetrySample],
    origin_seq: int,
    horizon_seconds: int,
    config: dict[str, float],
) -> float | None:
    history = _trailing_regular_history(run_samples, origin_seq)
    if len(history) < HOLT_WINTERS_MIN_HISTORY:
        return None
    origin = history[-1]
    model = HoltWintersForecaster(
        season_length=HOLT_WINTERS_SEASON_LENGTH,
        sample_interval_s=origin.sample_interval_target_s or 1.0,
        **config,
    )
    try:
        model.fit_samples(history, origin)
        return model.predict_horizon(float(horizon_seconds))
    except ValueError:
        return None


def _predict_targets(
    *,
    targets: list[CapacityTarget],
    grouped_samples: dict[str, list[TelemetrySample]],
    split_name: str,
    seasonal_seconds: float,
    holt_winters_config: dict[str, float],
    lightgbm_predictions: dict[tuple[str, int, int], float] | None = None,
) -> list[dict[str, Any]]:
    sample_index = {
        sample.run_id: {sample.sample_seq: sample for sample in run}
        for run_id, run in grouped_samples.items()
        for sample in run
    }
    output: list[dict[str, Any]] = []
    for target in targets:
        run = grouped_samples[target.run_id]
        by_seq = sample_index[target.run_id]
        origin = by_seq[target.origin_sample_seq]
        target_sample = by_seq[target.target_sample_seq]
        seasonal = seasonal_naive_forecast(
            run,
            origin,
            horizon_seconds=float(target.horizon_seconds),
            season_seconds=seasonal_seconds,
        )
        holt_winters = _fit_holt_winters_from_history(
            run,
            origin.sample_seq,
            target.horizon_seconds,
            holt_winters_config,
        )
        output.append(
            {
                "split": split_name,
                "run_id": target.run_id,
                "scenario_type": origin.scenario_type,
                "origin_sample_seq": origin.sample_seq,
                "origin_timestamp_utc": origin.timestamp_utc.isoformat(),
                "origin_elapsed_s": origin.elapsed_s,
                "origin_cadence_valid": origin.sample_cadence_valid,
                "target_sample_seq": target_sample.sample_seq,
                "target_timestamp_utc": target_sample.timestamp_utc.isoformat(),
                "target_elapsed_s": target_sample.elapsed_s,
                "target_cadence_valid": target_sample.sample_cadence_valid,
                "horizon_seconds": target.horizon_seconds,
                "origin_capacity_mbps": origin.configured_capacity_mbps,
                "actual_capacity_mbps": target.target_capacity_mbps,
                "persistence": persistence_forecast(origin),
                "seasonal_naive": seasonal,
                "holt_winters": holt_winters,
                "lightgbm": (
                    lightgbm_predictions.get(
                        (target.run_id, target.origin_sample_seq, target.horizon_seconds)
                    )
                    if lightgbm_predictions is not None
                    else None
                ),
            }
        )
    return output


def _lightgbm_feature_index(
    samples: list[TelemetrySample],
) -> dict[tuple[str, int], dict[str, float | None]]:
    return {
        (row.run_id, row.sample_seq): row.values
        for row in generate_features(samples)
    }


def _fit_lightgbm_models(
    *,
    training_targets: list[CapacityTarget],
    validation_targets: list[CapacityTarget],
    test_targets: list[CapacityTarget],
    feature_index: dict[tuple[str, int], dict[str, float | None]],
) -> tuple[
    dict[tuple[str, int, int], float],
    dict[int, dict[str, int | float]],
    dict[int, list[dict[str, int | float]]],
    dict[int, LightGBMForecaster],
]:
    predictions: dict[tuple[str, int, int], float] = {}
    selected_configs: dict[int, dict[str, int | float]] = {}
    candidate_scores: dict[int, list[dict[str, int | float]]] = {}
    models: dict[int, LightGBMForecaster] = {}

    for horizon in DEFAULT_HORIZONS_SECONDS:
        training = [
            target
            for target in training_targets
            if target.horizon_seconds == horizon
        ]
        validation = [
            target
            for target in validation_targets
            if target.horizon_seconds == horizon
        ]
        if not training or not validation:
            raise ValueError(
                f"LightGBM +{horizon}s requires training and validation targets"
            )
        training_features = [
            feature_index[(target.run_id, target.origin_sample_seq)]
            for target in training
        ]
        training_labels = [target.target_capacity_mbps for target in training]
        validation_features = [
            feature_index[(target.run_id, target.origin_sample_seq)]
            for target in validation
        ]
        validation_labels = [target.target_capacity_mbps for target in validation]

        scores: list[dict[str, int | float]] = []
        for n_estimators in LIGHTGBM_N_ESTIMATORS_CANDIDATES:
            model = LightGBMForecaster(
                **LIGHTGBM_PARAMS, n_estimators=n_estimators
            ).fit(training_features, training_labels)
            predicted = model.predict(validation_features)
            scores.append(
                {
                    "n_estimators": n_estimators,
                    "count": len(validation_labels),
                    "mae": sum(
                        abs(actual - estimate)
                        for actual, estimate in zip(validation_labels, predicted)
                    )
                    / len(validation_labels),
                }
            )
        selected = min(scores, key=lambda score: (score["mae"], -score["count"]))
        config: dict[str, int | float] = {
            **LIGHTGBM_PARAMS,
            "n_estimators": int(selected["n_estimators"]),
        }
        final_model = LightGBMForecaster(**config).fit(
            training_features, training_labels
        )
        models[horizon] = final_model
        selected_configs[horizon] = config
        candidate_scores[horizon] = scores

        for target in (*validation, *[
            item for item in test_targets if item.horizon_seconds == horizon
        ]):
            feature = feature_index[(target.run_id, target.origin_sample_seq)]
            predictions[
                (target.run_id, target.origin_sample_seq, target.horizon_seconds)
            ] = final_model.predict([feature])[0]

    return predictions, selected_configs, candidate_scores, models


def _select_seasonal_period(
    validation_predictions: list[dict[str, Any]],
) -> tuple[float, list[dict[str, Any]]]:
    scores: list[dict[str, Any]] = []
    for season in SEASON_CANDIDATES_SECONDS:
        actual: list[float] = []
        predicted: list[float] = []
        for row in validation_predictions:
            sample = row["_origin"]
            values = row["_run"]
            value = seasonal_naive_forecast(
                values,
                sample,
                horizon_seconds=float(row["horizon_seconds"]),
                season_seconds=season,
            )
            if value is not None:
                actual.append(float(row["actual_capacity_mbps"]))
                predicted.append(value)
        scores.append(
            {
                "season_seconds": season,
                "count": len(actual),
                "mae": (
                    sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)
                    if actual
                    else None
                ),
            }
        )
    eligible = [row for row in scores if row["mae"] is not None]
    if not eligible:
        raise ValueError("seasonal-naive has no valid validation predictions")
    selected = min(eligible, key=lambda row: (row["mae"], -row["count"]))
    return float(selected["season_seconds"]), scores


def _select_holt_winters_config(
    validation_targets: list[CapacityTarget],
    validation_runs: dict[str, list[TelemetrySample]],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    scores: list[dict[str, Any]] = []
    for config in HOLT_WINTERS_CANDIDATES:
        actual: list[float] = []
        predicted: list[float] = []
        for target in validation_targets:
            forecast = _fit_holt_winters_from_history(
                validation_runs[target.run_id],
                target.origin_sample_seq,
                target.horizon_seconds,
                config,
            )
            if forecast is not None:
                actual.append(target.target_capacity_mbps)
                predicted.append(forecast)
        scores.append(
            {
                "config": config,
                "count": len(actual),
                "mae": (
                    sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)
                    if actual
                    else None
                ),
            }
        )
    eligible = [row for row in scores if row["mae"] is not None]
    if not eligible:
        raise ValueError(
            "Holt-Winters has insufficient contiguous validation history to "
            "select smoothing parameters"
        )
    selected = min(eligible, key=lambda row: (row["mae"], -row["count"]))
    return dict(selected["config"]), scores


def _train_holt_winters_artifacts(
    training_runs: dict[str, list[TelemetrySample]],
    config: dict[str, float],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for run_id, run in training_runs.items():
        segment: list[TelemetrySample] = []
        segments: list[list[TelemetrySample]] = []
        for sample in run:
            if sample.configured_capacity_mbps is None:
                segment = []
            elif segment and (
                sample.sample_seq != segment[-1].sample_seq + 1
                or not sample.sample_cadence_valid
            ):
                if len(segment) >= HOLT_WINTERS_MIN_HISTORY:
                    segments.append(segment)
                segment = [sample]
            else:
                segment.append(sample)
        if len(segment) >= HOLT_WINTERS_MIN_HISTORY:
            segments.append(segment)
        for segment_index, history in enumerate(segments):
            model = HoltWintersForecaster(
                season_length=HOLT_WINTERS_SEASON_LENGTH,
                sample_interval_s=history[-1].sample_interval_target_s or 1.0,
                **config,
            ).fit([float(item.configured_capacity_mbps) for item in history])
            artifacts.append(
                {
                    "run_id": run_id,
                    "segment_index": segment_index,
                    "start_sample_seq": history[0].sample_seq,
                    "end_sample_seq": history[-1].sample_seq,
                    "observations": len(history),
                    "level": model._level,
                    "trend": model._trend,
                    "seasonals": model._seasonals,
                }
            )
    return artifacts


def _event_lead_seconds(
    run: list[TelemetrySample], row: dict[str, Any]
) -> float | None:
    current = float(row["origin_capacity_mbps"])
    origin_elapsed = float(row["origin_elapsed_s"])
    target_elapsed = float(row["target_elapsed_s"])
    previous = current
    for sample in run:
        if sample.elapsed_s <= origin_elapsed:
            continue
        if sample.elapsed_s > target_elapsed:
            break
        capacity = sample.configured_capacity_mbps
        if capacity is None:
            return None
        if capacity != previous:
            return sample.elapsed_s - origin_elapsed
        previous = capacity
    return None


def _metric_rows(
    rows: list[dict[str, Any]],
    grouped_samples: dict[str, list[TelemetrySample]],
    split_name: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    scenarios = sorted({row["scenario_type"] for row in rows})
    for model_name in MODEL_NAMES:
        for horizon in DEFAULT_HORIZONS_SECONDS:
            for scenario in [*scenarios, "all"]:
                selected = [
                    row
                    for row in rows
                    if row["horizon_seconds"] == horizon
                    and (scenario == "all" or row["scenario_type"] == scenario)
                    and row[model_name] is not None
                ]
                actual = [float(row["actual_capacity_mbps"]) for row in selected]
                predicted = [float(row[model_name]) for row in selected]
                persistence = [
                    float(row["persistence"]) for row in selected
                ]
                if selected:
                    metrics = regression_metrics(
                        actual, predicted, persistence_predicted=persistence
                    )
                    mae: float | None = metrics.mae
                    rmse: float | None = metrics.rmse
                    bias: float | None = metrics.bias
                    improvement = metrics.improvement_over_persistence_mae
                else:
                    mae = rmse = bias = improvement = None

                changed_rows = [
                    row
                    for row in selected
                    if row["actual_capacity_mbps"] != row["origin_capacity_mbps"]
                ]
                correct_directions = 0
                leads: list[float] = []
                by_run = grouped_samples
                for row in changed_rows:
                    actual_delta = (
                        float(row["actual_capacity_mbps"])
                        - float(row["origin_capacity_mbps"])
                    )
                    predicted_delta = (
                        float(row[model_name]) - float(row["origin_capacity_mbps"])
                    )
                    if (actual_delta > 0 and predicted_delta > 0) or (
                        actual_delta < 0 and predicted_delta < 0
                    ):
                        correct_directions += 1
                    lead = _event_lead_seconds(by_run[row["run_id"]], row)
                    if lead is not None:
                        leads.append(lead)
                output.append(
                    {
                        "split": split_name,
                        "scenario": scenario,
                        "model": model_name,
                        "horizon_seconds": horizon,
                        "count": len(selected),
                        "mae_mbps": mae,
                        "rmse_mbps": rmse,
                        "bias_mbps": bias,
                        "improvement_over_persistence_mae": improvement,
                        "capacity_change_pairs": len(changed_rows),
                        "change_direction_accuracy": (
                            correct_directions / len(changed_rows)
                            if changed_rows
                            else None
                        ),
                        "mean_observed_change_lead_s": (
                            statistics.fmean(leads) if leads else None
                        ),
                    }
                )
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("x", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_svg(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    width, height = 900, 480
    left, right, top, bottom = 70, 25, 45, 55
    plot_width, plot_height = width - left - right, height - top - bottom
    values = [
        float(row[key])
        for row in rows
        for key in ("actual_capacity_mbps", "persistence", "seasonal_naive", "holt_winters")
        if row.get(key) is not None
    ]
    if not values:
        values = [0.0, 1.0]
    minimum, maximum = min(values), max(values)
    if math.isclose(minimum, maximum):
        minimum -= 1
        maximum += 1
    x_values = [float(row["origin_elapsed_s"]) for row in rows]
    min_x, max_x = min(x_values, default=0.0), max(x_values, default=1.0)
    if math.isclose(min_x, max_x):
        max_x += 1

    def point(row: dict[str, Any], key: str) -> tuple[float, float]:
        x = left + (float(row["origin_elapsed_s"]) - min_x) / (max_x - min_x) * plot_width
        y = top + (maximum - float(row[key])) / (maximum - minimum) * plot_height
        return x, y

    colors = {
        "actual_capacity_mbps": "#111827",
        "persistence": "#2563eb",
        "seasonal_naive": "#16a34a",
        "holt_winters": "#dc2626",
    }
    labels = {
        "actual_capacity_mbps": "Actual",
        "persistence": "Persistence",
        "seasonal_naive": "Seasonal naive",
        "holt_winters": "Holt-Winters",
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="25" text-anchor="middle" font-family="sans-serif" font-size="16">{html.escape(title)}</text>',
        f'<path d="M {left} {top} V {top+plot_height} H {left+plot_width}" fill="none" stroke="#64748b"/>',
        f'<text x="{left+plot_width/2}" y="{height-12}" text-anchor="middle" font-family="sans-serif" font-size="12">Origin elapsed time (s)</text>',
        f'<text x="18" y="{top+plot_height/2}" transform="rotate(-90 18 {top+plot_height/2})" text-anchor="middle" font-family="sans-serif" font-size="12">Configured capacity (Mbps)</text>',
    ]
    for key in colors:
        present = [row for row in rows if row.get(key) is not None]
        if not present:
            continue
        coords = [point(row, key) for row in present]
        path_data = " ".join(
            f"{'M' if i == 0 else 'L'} {x:.1f} {y:.1f}"
            for i, (x, y) in enumerate(coords)
        )
        parts.append(
            f'<path d="{path_data}" fill="none" stroke="{colors[key]}" stroke-width="2"/>'
        )
        for x, y in coords:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.8" fill="{colors[key]}"/>'
            )
        parts.append(
            f'<text x="{left+20+list(colors).index(key)*160}" y="{height-35}" '
            f'font-family="sans-serif" font-size="12" fill="{colors[key]}">'
            f'{html.escape(labels[key])}</text>'
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _write_report(
    path: Path,
    *,
    split: RunSplit,
    eligible_paths: list[Path],
    excluded: list[dict[str, str]],
    selected_season: float,
    seasonal_scores: list[dict[str, Any]],
    selected_hw: dict[str, float],
    hw_scores: list[dict[str, Any]],
    train_hw_states: list[dict[str, Any]],
    validation_metrics: list[dict[str, Any]],
    test_metrics: list[dict[str, Any]],
    prediction_path: Path,
    plot_paths: list[Path],
    lightgbm_available: bool,
    lightgbm_configs: dict[int, dict[str, int | float]],
    lightgbm_scores: dict[int, list[dict[str, int | float]]],
) -> None:
    lines = [
        "# Preliminary capacity forecasting evaluation",
        "",
        "Offline research result; not production-ready and not integrated into the live controller.",
        "",
        "## Dataset and split",
        "",
        f"- Integrity-valid CSV/manifest pairs: **{len(eligible_paths)}**",
        f"- Training runs: {len(split.train_run_ids)}",
        f"- Validation runs: {len(split.validation_run_ids)}",
        f"- Test runs: {len(split.test_run_ids)}",
        f"- Excluded CSV files: {len(excluded)}",
        "- Target: configured shared root-TBF capacity (Mbps), never observed throughput.",
        "- Target matching uses actual timestamps and real observations only; no interpolation or synthetic samples.",
        "",
        "### Run IDs",
        "",
        f"- Train: `{', '.join(split.train_run_ids)}`",
        f"- Validation: `{', '.join(split.validation_run_ids)}`",
        f"- Test: `{', '.join(split.test_run_ids)}`",
        "",
        "### Exclusions",
        "",
    ]
    lines.extend(
        f"- `{item['file']}`: {item['reason']}" for item in excluded
    )
    if not excluded:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Validation-selected configurations",
            "",
            f"- Seasonal-naive period: **{selected_season:g} seconds**",
            f"- Seasonal-naive candidate scores: `{json.dumps(seasonal_scores, sort_keys=True)}`",
            f"- Holt-Winters: season length {HOLT_WINTERS_SEASON_LENGTH} samples; selected smoothing `{json.dumps(selected_hw, sort_keys=True)}`",
            f"- Holt-Winters validation candidates: `{json.dumps(hw_scores, sort_keys=True)}`",
            f"- Holt-Winters training-only contiguous states persisted: **{len(train_hw_states)}**",
            (
                f"- LightGBM selected configurations by horizon: `{json.dumps(lightgbm_configs, sort_keys=True)}`"
                if lightgbm_available
                else "- LightGBM: **not installed; not trained**"
            ),
            (
                f"- LightGBM validation candidate scores: `{json.dumps(lightgbm_scores, sort_keys=True)}`"
                if lightgbm_available
                else ""
            ),
            "",
            "## Test metrics",
            "",
            "| Scenario | Model | Horizon (s) | Pairs | MAE | RMSE | Bias | Improvement vs persistence | Changed pairs | Direction accuracy | Mean change lead (s) |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in test_metrics:
        lines.append(
            "| "
            + " | ".join(
                _fmt(row[key])
                for key in (
                    "scenario",
                    "model",
                    "horizon_seconds",
                    "count",
                    "mae_mbps",
                    "rmse_mbps",
                    "bias_mbps",
                    "improvement_over_persistence_mae",
                    "capacity_change_pairs",
                    "change_direction_accuracy",
                    "mean_observed_change_lead_s",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Validation metrics",
            "",
            "| Scenario | Model | Horizon (s) | Pairs | MAE | RMSE | Bias | Improvement vs persistence | Changed pairs | Direction accuracy | Mean change lead (s) |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in validation_metrics:
        lines.append(
            "| "
            + " | ".join(
                _fmt(row[key])
                for key in (
                    "scenario",
                    "model",
                    "horizon_seconds",
                    "count",
                    "mae_mbps",
                    "rmse_mbps",
                    "bias_mbps",
                    "improvement_over_persistence_mae",
                    "capacity_change_pairs",
                    "change_direction_accuracy",
                    "mean_observed_change_lead_s",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Validation metrics were used to select Holt-Winters smoothing. Seasonal-naive period was selected by validation MAE, but the selected 60-second period had only six validation forecasts; treat its test result as low-coverage and preliminary. Test metrics were computed after configuration selection and are listed in the preceding table. The test data was also inspected in a prior post-hoc seasonal-naive diagnostic, so this is exploratory rather than an untouched final test.",
            "",
            "## Direction and timing",
            "",
            "Capacity-change direction is assessed only for target pairs whose configured capacity differs from the origin. Mean change lead is the measured time from forecast origin to the first observed capacity transition within the target interval. A scripted schedule is known to the experimenter but is not supplied as a model feature; an unannounced abrupt change cannot be predicted from history alone unless its precursor is observable.",
            "",
            "## Leakage controls",
            "",
            "- Files are independently loaded through the manifest-aware schema validator; malformed/mismatched runs are excluded.",
            "- Run IDs are assigned chronologically to disjoint 6/2/2 train/validation/test groups before target construction.",
            "- Targets use only configured TBF labels at future timestamps in the same run; throughput is never used as target.",
            "- Persistence and seasonal-naive use only capacity observations at or before each origin.",
            "- Holt-Winters smoothing configuration is selected on validation. Its per-origin filter state uses only the contiguous, cadence-valid history through that origin; forecasts are omitted when that history is insufficient.",
            "- LightGBM regressors are fit only on training-run examples; estimator count is selected on validation for each horizon.",
            "",
            "## Limitations and recommendations",
            "",
            "- The test runs were inspected in a post-hoc seasonal-naive diagnostic before this evaluation. Do not treat these metrics as a pristine final holdout; collect fresh independent test runs for final claims.",
            "- The test split contains only periodic runs; the validation split contains only step runs. This is a run-disjoint chronological evaluation, not broad scenario-generalization evidence.",
            "- Cadence-invalid intervals are preserved but cannot be used to form regular Holt-Winters history. No samples are inserted to repair gaps.",
            "- The test runs have fewer than the 40 contiguous samples required to initialize Holt-Winters with a 20-sample seasonal period, so it has no test forecasts or test metrics.",
            "- The experiment uses scripted, repeating TBF settings. Performance does not demonstrate prediction of genuinely unexpected ISP capacity changes.",
            "- Test results are based on only two independent runs and short 60-second traces.",
            (
                "- LightGBM was installed in the selected `.venv` for this approved offline evaluation."
                if lightgbm_available
                else "- LightGBM remains unavailable in the selected `.venv`; no dependency was installed."
            ),
            "- Collect more independently seeded runs, including held-out transition timings/periods and additional scenario families, before stronger model claims.",
            "",
            "## Artifacts",
            "",
            f"- Predictions: `{prediction_path.name}`",
            "- Metrics: `metrics.csv`",
            "- Actual-vs-predicted plots:",
        ]
    )
    lines.extend(f"  - `{p.name}`" for p in plot_paths)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(output_dir: Path) -> Path:
    samples, excluded, eligible_paths = _load_eligible_runs(RAW_DATA_DIR)
    split = chronological_run_split(samples)
    training_runs = _run_samples(samples, split.train_run_ids)
    validation_runs = _run_samples(samples, split.validation_run_ids)
    test_runs = _run_samples(samples, split.test_run_ids)

    validation_targets = generate_capacity_targets(
        [sample for run in validation_runs.values() for sample in run]
    )
    test_targets = generate_capacity_targets(
        [sample for run in test_runs.values() for sample in run]
    )
    if not validation_targets or not test_targets:
        raise ValueError("validation and test splits must have target pairs")

    validation_candidates = []
    validation_aux = []
    for target in validation_targets:
        validation_aux.append(
            {
                "target": target,
                "_origin": next(
                    sample
                    for sample in validation_runs[target.run_id]
                    if sample.sample_seq == target.origin_sample_seq
                ),
                "_run": validation_runs[target.run_id],
                "actual_capacity_mbps": target.target_capacity_mbps,
                "horizon_seconds": target.horizon_seconds,
            }
        )
    selected_season, seasonal_scores = _select_seasonal_period(validation_aux)
    selected_hw, hw_scores = _select_holt_winters_config(
        validation_targets, validation_runs
    )
    training_targets = generate_capacity_targets(
        [sample for run in training_runs.values() for sample in run]
    )

    # Final model state artifacts are fitted only from training runs.
    train_hw_states = _train_holt_winters_artifacts(training_runs, selected_hw)
    if not train_hw_states:
        raise ValueError(
            "no training run has enough contiguous cadence-valid history for "
            "Holt-Winters"
        )

    try:
        import lightgbm
    except ImportError:
        lightgbm_available = False
        lightgbm_version = None
        lightgbm_predictions = None
        lightgbm_configs = {}
        lightgbm_scores = {}
        lightgbm_models = {}
    else:
        lightgbm_available = True
        lightgbm_version = lightgbm.__version__
        (
            lightgbm_predictions,
            lightgbm_configs,
            lightgbm_scores,
            lightgbm_models,
        ) = _fit_lightgbm_models(
            training_targets=training_targets,
            validation_targets=validation_targets,
            test_targets=test_targets,
            feature_index=_lightgbm_feature_index(samples),
        )

    validation_rows = _predict_targets(
        targets=validation_targets,
        grouped_samples=validation_runs,
        split_name="validation",
        seasonal_seconds=selected_season,
        holt_winters_config=selected_hw,
        lightgbm_predictions=lightgbm_predictions,
    )
    test_rows = _predict_targets(
        targets=test_targets,
        grouped_samples=test_runs,
        split_name="test",
        seasonal_seconds=selected_season,
        holt_winters_config=selected_hw,
        lightgbm_predictions=lightgbm_predictions,
    )
    validation_metrics = _metric_rows(
        validation_rows, validation_runs, "validation"
    )
    test_metrics = _metric_rows(test_rows, test_runs, "test")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=False, exist_ok=False)
    if lightgbm_models:
        models_dir = output_dir / "models"
        models_dir.mkdir()
        for horizon, model in lightgbm_models.items():
            model.save_model(str(models_dir / f"lightgbm_horizon_{horizon}s.txt"))
    predictions = validation_rows + test_rows
    prediction_path = output_dir / "predictions.csv"
    _write_csv(prediction_path, predictions)
    _write_csv(
        output_dir / "metrics.csv",
        validation_metrics + test_metrics,
    )

    split_data = {
        "train_run_ids": split.train_run_ids,
        "validation_run_ids": split.validation_run_ids,
        "test_run_ids": split.test_run_ids,
    }
    (output_dir / "split.json").write_text(
        json.dumps(split_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    config = {
        "target": "configured shared root-TBF capacity in Mbps",
        "horizons_seconds": DEFAULT_HORIZONS_SECONDS,
        "target_timestamp_tolerance_s": 0.25,
        "seasonal_naive_candidates_seconds": SEASON_CANDIDATES_SECONDS,
        "selected_seasonal_naive_seconds": selected_season,
        "holt_winters_season_length_samples": HOLT_WINTERS_SEASON_LENGTH,
        "holt_winters_candidates": HOLT_WINTERS_CANDIDATES,
        "selected_holt_winters": selected_hw,
        "lightgbm_available": lightgbm_available,
        "lightgbm_version": lightgbm_version,
        "lightgbm_selected_configs": lightgbm_configs,
        "training_runs": len(split.train_run_ids),
        "validation_runs": len(split.validation_run_ids),
        "test_runs": len(split.test_run_ids),
        "raw_csv_paths": [str(path) for path in eligible_paths],
    }
    (output_dir / "configuration.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "selection_scores.json").write_text(
        json.dumps(
            {
                "seasonal_naive": seasonal_scores,
                "holt_winters": hw_scores,
                "lightgbm": lightgbm_scores,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "holt_winters_training_states.json").write_text(
        json.dumps(
            {
                "season_length_samples": HOLT_WINTERS_SEASON_LENGTH,
                "config": selected_hw,
                "trained_states": train_hw_states,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "excluded_runs.json").write_text(
        json.dumps(excluded, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    plot_paths: list[Path] = []
    for run_id in split.test_run_ids:
        run_rows = [row for row in test_rows if row["run_id"] == run_id]
        for horizon in DEFAULT_HORIZONS_SECONDS:
            selected = [
                row for row in run_rows if row["horizon_seconds"] == horizon
            ]
            plot_path = output_dir / f"actual_vs_predicted_{run_id[:8]}_{horizon}s.svg"
            _write_svg(
                plot_path,
                selected,
                f"{run_rows[0]['scenario_type']} run {run_id[:8]} +{horizon}s",
            )
            plot_paths.append(plot_path)

    _write_report(
        output_dir / "report.md",
        split=split,
        eligible_paths=eligible_paths,
        excluded=excluded,
        selected_season=selected_season,
        seasonal_scores=seasonal_scores,
        selected_hw=selected_hw,
        hw_scores=hw_scores,
        train_hw_states=train_hw_states,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        prediction_path=prediction_path,
        plot_paths=plot_paths,
        lightgbm_available=lightgbm_available,
        lightgbm_configs=lightgbm_configs,
        lightgbm_scores=lightgbm_scores,
    )
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="new, non-existing directory for this reproducible evaluation",
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.output_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"offline evaluation failed: {error}\n")
    print(f"results={result}")
    print(f"report={result / 'report.md'}")
    print(f"predictions={result / 'predictions.csv'}")
    print(f"metrics={result / 'metrics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

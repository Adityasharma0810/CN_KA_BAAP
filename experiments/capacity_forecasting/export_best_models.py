#!/usr/bin/env python3
"""Export validation-selected, pickleable per-horizon forecasting models."""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml.forecasting.features import DEFAULT_WINDOWS, feature_names, generate_features
from ml.forecasting.lightgbm_model import LightGBMForecaster
from ml.forecasting.persistence_model import PersistenceCapacityForecaster
from ml.forecasting.schema import TelemetrySample, load_collector_csv
from ml.forecasting.targets import DEFAULT_HORIZONS_SECONDS

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = (
    REPOSITORY_ROOT / "experiments" / "capacity_forecasting" / "models" / "best"
)
MIN_VALIDATION_PAIRS = 30
MIN_VALIDATION_COVERAGE = 0.8
PICKLE_MODEL_NAMES = {
    "lightgbm": "LightGBMForecaster",
    "persistence": "PersistenceCapacityForecaster",
}


def _read_validation_predictions(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["split"] != "validation":
                break
            rows.append(row)
    if not rows:
        raise ValueError(f"no validation predictions found in {path}")
    return rows


def _validation_metrics(
    rows: list[dict[str, str]],
) -> tuple[dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    scores: dict[int, list[dict[str, Any]]] = {}
    winners: dict[int, dict[str, Any]] = {}
    for horizon in DEFAULT_HORIZONS_SECONDS:
        horizon_rows = [
            row for row in rows if int(row["horizon_seconds"]) == horizon
        ]
        total = len(horizon_rows)
        required = max(
            MIN_VALIDATION_PAIRS,
            math.ceil(total * MIN_VALIDATION_COVERAGE),
        )
        candidates: list[dict[str, Any]] = []
        for model_name in ("persistence", "seasonal_naive", "holt_winters", "lightgbm"):
            selected = [
                row
                for row in horizon_rows
                if row.get(model_name, "").strip()
            ]
            actual = [float(row["actual_capacity_mbps"]) for row in selected]
            predicted = [float(row[model_name]) for row in selected]
            count = len(selected)
            mae = (
                sum(abs(truth - estimate) for truth, estimate in zip(actual, predicted))
                / count
                if count
                else None
            )
            rmse = (
                math.sqrt(
                    sum((estimate - truth) ** 2 for truth, estimate in zip(actual, predicted))
                    / count
                )
                if count
                else None
            )
            bias = (
                sum(estimate - truth for truth, estimate in zip(actual, predicted))
                / count
                if count
                else None
            )
            candidates.append(
                {
                    "model_name": model_name,
                    "count": count,
                    "total_validation_pairs": total,
                    "coverage_fraction": count / total if total else 0.0,
                    "required_pairs": required,
                    "eligible": count >= required,
                    "mae_mbps": mae,
                    "rmse_mbps": rmse,
                    "bias_mbps": bias,
                }
            )
        eligible = [
            candidate
            for candidate in candidates
            if candidate["eligible"]
            and candidate["model_name"] in PICKLE_MODEL_NAMES
        ]
        scores[horizon] = candidates
        if eligible:
            winners[horizon] = min(
                eligible,
                key=lambda candidate: (
                    candidate["mae_mbps"],
                    -candidate["count"],
                    candidate["model_name"],
                ),
            )
    return winners, scores


def _load_validation_samples(
    raw_dir: Path, validation_run_ids: list[str]
) -> list[TelemetrySample]:
    samples: list[TelemetrySample] = []
    for run_id in validation_run_ids:
        path = raw_dir / f"capacity_{run_id}.csv"
        run_samples = load_collector_csv(path)
        if any(sample.run_id != run_id for sample in run_samples):
            raise ValueError(f"validation CSV {path.name} contains a different run ID")
        if not all(
            sample.capacity_config_valid
            and sample.configured_capacity_mbps is not None
            for sample in run_samples
        ):
            raise ValueError(f"validation run {run_id} has invalid capacity labels")
        samples.extend(run_samples)
    return samples


def _verify_pickles_in_clean_process(
    output_dir: Path,
    validation_features: dict[tuple[str, int], dict[str, float | None]],
    validation_rows: list[dict[str, str]],
    winners: dict[int, dict[str, Any]],
) -> None:
    checks: dict[str, Any] = {}
    for horizon, winner in winners.items():
        name = winner["model_name"]
        rows = [
            row
            for row in validation_rows
            if int(row["horizon_seconds"]) == horizon
            and row.get(name, "").strip()
        ]
        checks[str(horizon)] = {
            "features": [
                validation_features[(row["run_id"], int(row["origin_sample_seq"]))]
                for row in rows
            ],
            "expected": [float(row[name]) for row in rows],
        }

    verifier = """
import json
import math
import pickle
import sys
from pathlib import Path

payload = json.load(sys.stdin)
root = Path(payload["output_dir"])
result = {}
for horizon, check in payload["checks"].items():
    with (root / f"best_model_{horizon}s.pkl").open("rb") as stream:
        model = pickle.load(stream)
    actual = model.predict(check["features"])
    expected = check["expected"]
    if len(actual) != len(expected) or not all(
        math.isclose(a, e, rel_tol=1e-12, abs_tol=1e-12)
        for a, e in zip(actual, expected)
    ):
        raise SystemExit(f"prediction mismatch for +{horizon}s after pickle reload")
    result[horizon] = len(actual)
print(json.dumps(result, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", verifier],
        input=json.dumps({"output_dir": str(output_dir), "checks": checks}),
        capture_output=True,
        check=True,
        cwd=REPOSITORY_ROOT,
        text=True,
    )
    verified_counts = json.loads(completed.stdout)
    for horizon, winner in winners.items():
        if verified_counts.get(str(horizon)) != winner["count"]:
            raise ValueError(
                f"clean-process verification count mismatch for +{horizon}s"
            )


def export_best_models(
    source_dir: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    raw_dir: Path = REPOSITORY_ROOT / "data" / "capacity_forecasting" / "raw",
) -> Path:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing model directory {output_dir}")
    split = json.loads((source_dir / "split.json").read_text(encoding="utf-8"))
    config = json.loads(
        (source_dir / "configuration.json").read_text(encoding="utf-8")
    )
    training_run_ids = split["train_run_ids"]
    validation_run_ids = split["validation_run_ids"]
    if (
        len(training_run_ids) != 6
        or len(validation_run_ids) != 2
        or set(training_run_ids) & set(validation_run_ids)
    ):
        raise ValueError("source artifacts do not contain the expected disjoint 6/2 split")

    validation_rows = _read_validation_predictions(source_dir / "predictions.csv")
    if {row["run_id"] for row in validation_rows} != set(validation_run_ids):
        raise ValueError("validation predictions do not match validation run IDs")
    winners, scores = _validation_metrics(validation_rows)
    validation_samples = _load_validation_samples(raw_dir, validation_run_ids)
    feature_rows = generate_features(validation_samples)
    expected_feature_names = feature_names()
    validation_features = {
        (row.run_id, row.sample_seq): row.values for row in feature_rows
    }

    output_dir.mkdir(parents=True, exist_ok=False)
    horizon_metadata: dict[str, Any] = {}
    saved_winners: dict[int, dict[str, Any]] = {}
    lightgbm_version: str | None = None
    numpy_version: str | None = None
    try:
        import lightgbm
        import numpy

        lightgbm_version = lightgbm.__version__
        numpy_version = numpy.__version__
    except ImportError:
        pass

    for horizon in DEFAULT_HORIZONS_SECONDS:
        winner = winners.get(horizon)
        if winner is None:
            horizon_metadata[str(horizon)] = {
                "status": "no_validated_best_model",
                "forecast_horizon_seconds": horizon,
                "reason": (
                    "No persistable candidate met the minimum validation coverage "
                    f"of {MIN_VALIDATION_PAIRS} pairs and "
                    f"{MIN_VALIDATION_COVERAGE:.0%} of validation targets."
                ),
                "candidate_metrics": scores[horizon],
            }
            continue

        model_name = winner["model_name"]
        model_path = output_dir / f"best_model_{horizon}s.pkl"
        if model_name == "lightgbm":
            params = config["lightgbm_selected_configs"][str(horizon)]
            source_model = (
                source_dir / "models" / f"lightgbm_horizon_{horizon}s.txt"
            )
            model = LightGBMForecaster.from_model_file(
                source_model, **params
            )
            if model.feature_names != expected_feature_names:
                raise ValueError(
                    f"LightGBM feature names/order mismatch for +{horizon}s"
                )
            validation_rows_for_model = [
                row
                for row in validation_rows
                if int(row["horizon_seconds"]) == horizon
                and row.get("lightgbm", "").strip()
            ]
            model_features = [
                validation_features[(row["run_id"], int(row["origin_sample_seq"]))]
                for row in validation_rows_for_model
            ]
            model_predictions = model.predict(model_features)
            saved_predictions = [
                float(row["lightgbm"]) for row in validation_rows_for_model
            ]
            if any(
                not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
                for actual, expected in zip(model_predictions, saved_predictions)
            ):
                raise ValueError(
                    f"saved LightGBM model does not reproduce validation forecasts "
                    f"for +{horizon}s"
                )
            model_type = "LightGBM native Booster wrapped by LightGBMForecaster"
            model_config: dict[str, Any] = params
            model_feature_names = list(model.feature_names or ())
        else:
            model = PersistenceCapacityForecaster()
            model.feature_names = expected_feature_names
            model_type = "PersistenceCapacityForecaster"
            model_config = {"forecast": "configured_capacity_at_origin"}
            model_feature_names = list(expected_feature_names)

        with model_path.open("wb") as stream:
            pickle.dump(model, stream, protocol=pickle.HIGHEST_PROTOCOL)
        saved_winners[horizon] = winner
        horizon_metadata[str(horizon)] = {
            "status": "best_model_saved",
            "model_name": model_name,
            "model_type": model_type,
            "artifact": model_path.name,
            "forecast_horizon_seconds": horizon,
            "feature_names": model_feature_names,
            "training_run_ids": training_run_ids,
            "validation_metrics": {
                key: winner[key]
                for key in (
                    "count",
                    "total_validation_pairs",
                    "coverage_fraction",
                    "mae_mbps",
                    "rmse_mbps",
                    "bias_mbps",
                )
            },
            "training_configuration": model_config,
            "selection_policy": {
                "metric": "validation MAE (Mbps)",
                "minimum_validation_pairs": MIN_VALIDATION_PAIRS,
                "minimum_validation_coverage_fraction": MIN_VALIDATION_COVERAGE,
                "eligible_candidates": [
                    candidate["model_name"]
                    for candidate in scores[horizon]
                    if candidate["eligible"]
                    and candidate["model_name"] in PICKLE_MODEL_NAMES
                ],
            },
            "candidate_validation_metrics": scores[horizon],
        }

    _verify_pickles_in_clean_process(
        output_dir, validation_features, validation_rows, saved_winners
    )
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_evaluation_directory": str(source_dir),
        "selection_data": (
            "validation prediction rows only; no test CSVs or test metrics were loaded"
        ),
        "training_run_ids": training_run_ids,
        "validation_run_ids": validation_run_ids,
        "feature_configuration": {
            "generator": "ml.forecasting.features.generate_features",
            "windows": list(DEFAULT_WINDOWS),
            "feature_names_order": list(expected_feature_names),
            "causal": True,
            "missing_measurements": (
                "remain null; LightGBM preprocessing converts null values to NaN; "
                "no imputation or scaling"
            ),
            "cadence_gaps": (
                "lags and rolling windows crossing missing/non-cadence-valid "
                "samples remain null"
            ),
        },
        "dependency_versions": {
            "python": platform.python_version(),
            "lightgbm": lightgbm_version,
            "numpy": numpy_version,
        },
        "pickle_protocol": pickle.HIGHEST_PROTOCOL,
        "clean_process_reload_verified": True,
        "models_by_horizon_seconds": horizon_metadata,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help="Prior offline result directory with validation metrics and model files",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--raw-dir", type=Path, default=REPOSITORY_ROOT / "data" / "capacity_forecasting" / "raw"
    )
    args = parser.parse_args(argv)
    result = export_best_models(args.source_dir, args.output_dir, args.raw_dir)
    print(f"best_models={result}")
    print(f"metadata={result / 'metadata.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

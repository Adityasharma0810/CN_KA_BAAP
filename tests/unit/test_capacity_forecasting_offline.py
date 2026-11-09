from datetime import datetime, timedelta, timezone

import pytest

from experiments.capacity_forecasting.train_offline import (
    HOLT_WINTERS_MIN_HISTORY,
    _fit_lightgbm_models,
    _fit_holt_winters_from_history,
    _predict_targets,
    _trailing_regular_history,
    _write_csv,
)
from experiments.capacity_forecasting.export_best_models import _validation_metrics
from ml.forecasting.schema import TelemetrySample
from ml.forecasting.targets import CapacityTarget


def make_run(*, count=45, cadence_breaks=()):
    start = datetime(2026, 11, 8, tzinfo=timezone.utc)
    breaks = set(cadence_breaks)
    samples = []
    for seq in range(count):
        capacity = 80.0 if (seq // 10) % 2 == 0 else 120.0
        samples.append(
            TelemetrySample(
                schema_version="1.1",
                scenario_id="periodic-test",
                scenario_type="periodic",
                run_id="offline-test-run",
                sample_seq=seq,
                timestamp_utc=start + timedelta(seconds=seq),
                elapsed_s=float(seq),
                sample_interval_s=1.0 if seq else None,
                configured_capacity_mbps=capacity,
                capacity_config_valid=True,
                sample_timing_valid=True,
                client_rates_mbps={
                    client: {"down": None, "up": None}
                    for client in ("client1", "client2", "client3")
                },
                aggregate_rates_mbps={"down": None, "up": None},
                sample_interval_target_s=1.0,
                sample_cadence_tolerance_s=0.25,
                sample_cadence_valid=seq > 0 and seq not in breaks,
            )
        )
    return samples


def test_holt_winters_history_ends_at_origin_and_breaks_on_invalid_cadence():
    samples = make_run(cadence_breaks={30})

    history = _trailing_regular_history(samples, 35)

    assert len(history) == 6
    assert history[0].sample_seq == 30
    assert history[-1].sample_seq == 35


def test_holt_winters_forecast_requires_sufficient_contiguous_origin_history():
    samples = make_run(count=80, cadence_breaks={35})

    assert _fit_holt_winters_from_history(
        samples, 39, 5, {"alpha": 0.3, "beta": 0.1, "gamma": 0.1}
    ) is None

    forecast = _fit_holt_winters_from_history(
        samples, 74, 5, {"alpha": 0.3, "beta": 0.1, "gamma": 0.1}
    )
    assert forecast is not None


def test_result_csv_creation_refuses_to_overwrite(tmp_path):
    output = tmp_path / "predictions.csv"
    _write_csv(output, [{"run_id": "first"}])

    with pytest.raises(FileExistsError):
        _write_csv(output, [{"run_id": "second"}])
    assert output.read_text(encoding="utf-8") == "run_id\nfirst\n"


def test_prediction_rows_preserve_the_run_level_split():
    samples = make_run(count=7)
    target = CapacityTarget(
        run_id=samples[0].run_id,
        origin_sample_seq=0,
        origin_elapsed_s=0.0,
        horizon_seconds=5,
        target_capacity_mbps=float(samples[5].configured_capacity_mbps),
        target_sample_seq=5,
    )

    predictions = _predict_targets(
        targets=[target],
        grouped_samples={samples[0].run_id: samples},
        split_name="test",
        seasonal_seconds=20.0,
        holt_winters_config={"alpha": 0.3, "beta": 0.1, "gamma": 0.1},
    )

    assert predictions[0]["split"] == "test"


def test_lightgbm_selects_on_validation_and_fits_only_training_targets(monkeypatch):
    class FakeForecaster:
        fit_targets = []

        def __init__(self, **params):
            self.params = params

        def fit(self, features, targets):
            self.fit_targets.append(list(targets))
            return self

        def predict(self, features):
            return [float(self.params["n_estimators"]) for _ in features]

    monkeypatch.setattr(
        "experiments.capacity_forecasting.train_offline.LightGBMForecaster",
        FakeForecaster,
    )
    targets = {
        run_id: [
            CapacityTarget(
                run_id=run_id,
                origin_sample_seq=0,
                origin_elapsed_s=0.0,
                horizon_seconds=horizon,
                target_capacity_mbps=capacity,
                target_sample_seq=horizon,
            )
            for horizon in (5, 10, 30)
        ]
        for run_id, capacity in (
            ("train", 80.0),
            ("validation", 50.0),
            ("test", 120.0),
        )
    }
    feature_index = {
        (run_id, 0): {"x": float(capacity)}
        for run_id, capacity in (
            ("train", 80),
            ("validation", 50),
            ("test", 120),
        )
    }

    predictions, configs, scores, _ = _fit_lightgbm_models(
        training_targets=targets["train"],
        validation_targets=targets["validation"],
        test_targets=targets["test"],
        feature_index=feature_index,
    )

    assert set(configs) == {5, 10, 30}
    assert all(config["n_estimators"] == 50 for config in configs.values())
    assert all(len(scores[horizon]) == 3 for horizon in scores)
    assert all(fitted_targets == [80.0] for fitted_targets in FakeForecaster.fit_targets)
    assert predictions[("validation", 0, 5)] == 50.0
    assert predictions[("test", 0, 5)] == 50.0


def test_best_model_selection_requires_minimum_validation_coverage():
    rows = [
        {
            "horizon_seconds": "5",
            "actual_capacity_mbps": "100",
            "persistence": "90",
            "seasonal_naive": "",
            "holt_winters": "",
            "lightgbm": "95",
        }
        for _ in range(40)
    ]
    for row in rows[:31]:
        row["lightgbm"] = ""

    winners, scores = _validation_metrics(rows)

    assert winners[5]["model_name"] == "persistence"
    assert winners[5]["count"] == 40
    assert next(item for item in scores[5] if item["model_name"] == "lightgbm")[
        "eligible"
    ] is False
    assert 10 not in winners


def test_best_model_selection_reports_no_model_for_low_pair_count():
    rows = [
        {
            "horizon_seconds": "30",
            "actual_capacity_mbps": "100",
            "persistence": "90",
            "seasonal_naive": "",
            "holt_winters": "",
            "lightgbm": "95",
        }
        for _ in range(12)
    ]

    winners, scores = _validation_metrics(rows)

    assert 30 not in winners
    assert all(not candidate["eligible"] for candidate in scores[30])

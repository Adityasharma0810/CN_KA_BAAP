import csv
import json
import math
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from experiments.capacity_forecasting.collect_gateway_telemetry import CSV_FIELDS
from ml.forecasting.baselines import (
    persistence_forecast,
    seasonal_naive_forecast,
)
from ml.forecasting.evaluation import chronological_run_split, regression_metrics
from ml.forecasting.features import feature_names, generate_features
from ml.forecasting.holt_winters import HoltWintersForecaster
from ml.forecasting.lightgbm_model import (
    LightGBMDependencyError,
    LightGBMForecaster,
)
from ml.forecasting.schema import (
    TelemetrySample,
    load_collector_csv,
)
from ml.forecasting.targets import generate_capacity_targets

START = datetime(2026, 11, 8, tzinfo=timezone.utc)


def sample(
    run_id="run-a",
    seq=0,
    elapsed=None,
    capacity=100.0,
    *,
    scenario_type="constant",
    down=1.0,
    up=0.25,
    timestamp=None,
):
    elapsed = float(seq) if elapsed is None else float(elapsed)
    return TelemetrySample(
        schema_version="1.1",
        scenario_id="scenario-a",
        scenario_type=scenario_type,
        run_id=run_id,
        sample_seq=seq,
        timestamp_utc=timestamp or START + timedelta(seconds=elapsed),
        elapsed_s=elapsed,
        sample_interval_s=1.0 if seq else None,
        configured_capacity_mbps=capacity,
        capacity_config_valid=capacity is not None,
        sample_timing_valid=True,
        client_rates_mbps={
            name: {"down": down, "up": up}
            for name in ("client1", "client2", "client3")
        },
        aggregate_rates_mbps={
            "down": down * 3 if down is not None else None,
            "up": up * 3 if up is not None else None,
        },
        sample_interval_target_s=1.0,
        sample_cadence_tolerance_s=0.25,
        sample_cadence_valid=seq > 0,
    )


def collector_row(
    seq, *, capacity=100.0, complete=True, valid=True, run_id="run-a"
):
    row = {field: "" for field in CSV_FIELDS}
    elapsed = float(seq)
    row.update(
        {
            "schema_version": "1.1",
            "scenario_id": "scenario-a",
            "scenario_type": "constant",
            "run_id": run_id,
            "random_seed": "7",
            "scenario_type": "constant",
            "traffic_profile": "test",
            "sample_seq": str(seq),
            "timestamp_utc": (START + timedelta(seconds=elapsed)).isoformat(),
            "elapsed_s": str(elapsed),
            "sample_interval_s": "" if seq == 0 else "1.0",
            "sample_interval_target_s": "1.0",
            "sample_cadence_tolerance_s": "0.25",
            "sample_cadence_valid": str(seq > 0),
            "sample_cadence_error": "first sample has no preceding interval" if seq == 0 else "",
            "configured_capacity_mbps": "" if capacity is None else str(capacity),
            "capacity_config_source": "tc",
            "capacity_config_valid": str(valid),
            "capacity_read_error": "" if valid else "invalid qdisc",
            "previous_configured_capacity_mbps": "",
            "capacity_changed": "",
            "sample_timing_valid": "True",
            "sample_timing_error": "",
            "aggregate_down_mbps": "",
            "aggregate_up_mbps": "",
            "run_complete": str(complete),
        }
    )
    for client in ("client1", "client2", "client3"):
        row.update(
            {
                f"{client}_down_bytes": str(seq * 125_000),
                f"{client}_up_bytes": str(seq * 31_250),
                f"{client}_down_mbps": "" if seq == 0 else "1.0",
                f"{client}_up_mbps": "" if seq == 0 else "0.25",
                f"{client}_down_rate_interval_s": "" if seq == 0 else "1.0",
                f"{client}_up_rate_interval_s": "" if seq == 0 else "1.0",
                f"{client}_down_counter_reset": "False",
                f"{client}_up_counter_reset": "False",
                f"{client}_read_valid": "True",
                f"{client}_read_error": "",
            }
        )
    if seq:
        row["aggregate_down_mbps"] = "3.0"
        row["aggregate_up_mbps"] = "0.75"
    return row


def write_collector_csv(path, rows, *, manifest_run_id=None, manifest_complete=None):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    first = rows[0]
    manifest = {
        "run_id": manifest_run_id or path.stem.removeprefix("capacity_"),
        "run_complete": (
            all(row["run_complete"].lower() == "true" for row in rows)
            if manifest_complete is None
            else manifest_complete
        ),
        "scenario_id": first["scenario_id"],
        "scenario_type": first["scenario_type"],
        "output_csv": str(path.resolve()),
    }
    path.with_name(f"{path.stem}_metadata.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_loader_preserves_run_and_timestamp_and_does_not_use_throughput_as_target(
    tmp_path,
):
    path = tmp_path / "capacity_run-a.csv"
    write_collector_csv(path, [collector_row(0), collector_row(1)])

    loaded = load_collector_csv(path)

    assert loaded[1].run_id == "run-a"
    assert loaded[1].timestamp_utc == START + timedelta(seconds=1)
    assert loaded[1].configured_capacity_mbps == 100.0
    assert loaded[1].aggregate_rates_mbps["down"] == 3.0
    assert loaded[0].aggregate_rates_mbps["down"] is None


def test_loader_rejects_incomplete_run_and_missing_schema_fields(tmp_path):
    incomplete = tmp_path / "capacity_run-a.csv"
    write_collector_csv(incomplete, [collector_row(0, complete=False)])
    with pytest.raises(ValueError, match="manifest does not mark the run complete"):
        load_collector_csv(incomplete)

    malformed = tmp_path / "capacity_run-a.csv"
    malformed.write_text("run_id,sample_seq\nrun-a,0\n", encoding="utf-8")
    malformed.with_name("capacity_run-a_metadata.json").write_text(
        '{"run_id":"run-a","run_complete":true}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="missing required columns"):
        load_collector_csv(malformed)


def test_loader_preserves_legacy_1_0_csv_but_does_not_assume_regular_cadence(
    tmp_path,
):
    path = tmp_path / "capacity_run-a.csv"
    row = collector_row(1)
    row["schema_version"] = "1.0"
    legacy_fields = [field for field in CSV_FIELDS if not field.startswith("sample_cadence_") and field != "sample_interval_target_s"]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=legacy_fields)
        writer.writeheader()
        writer.writerow({field: row[field] for field in legacy_fields})
    path.with_name("capacity_run-a_metadata.json").write_text(
        '{"run_id":"run-a","run_complete":true,"scenario_id":"scenario-a",'
        '"scenario_type":"constant","output_csv":"capacity_run-a.csv"}',
        encoding="utf-8",
    )

    loaded = load_collector_csv(path)

    assert len(loaded) == 1
    assert loaded[0].configured_capacity_mbps == 100.0
    assert loaded[0].sample_cadence_valid is False


def test_invalid_capacity_label_is_missing_not_zero(tmp_path):
    path = tmp_path / "capacity_run-a.csv"
    write_collector_csv(
        path,
        [collector_row(0, capacity=None, valid=False), collector_row(1)],
    )

    loaded = load_collector_csv(path)

    assert loaded[0].configured_capacity_mbps is None
    assert loaded[0].capacity_config_valid is False
    assert loaded[0].configured_capacity_mbps != 0


def test_loader_rejects_missing_or_mismatched_metadata_run_id(tmp_path):
    missing = tmp_path / "capacity_run.csv"
    missing.write_text("run_id\nrun\n", encoding="utf-8")
    with pytest.raises(ValueError, match="matching metadata manifest not found"):
        load_collector_csv(missing)

    path = tmp_path / "capacity_filename-run.csv"
    write_collector_csv(
        path,
        [collector_row(0, run_id="row-run")],
        manifest_run_id="filename-run",
    )
    with pytest.raises(ValueError, match="row run_id.*CSV filename run_id"):
        load_collector_csv(path)

    path = tmp_path / "capacity_run-a.csv"
    write_collector_csv(
        path,
        [collector_row(0), collector_row(1, run_id="second-row-run")],
        manifest_run_id="run-a",
    )
    with pytest.raises(ValueError, match="row run_id.*CSV filename run_id"):
        load_collector_csv(path)


def test_loader_rejects_manifest_mismatch_and_output_filename_mismatch(tmp_path):
    path = tmp_path / "capacity_run-a.csv"
    write_collector_csv(path, [collector_row(0)], manifest_run_id="other-run")
    with pytest.raises(ValueError, match="manifest run_id"):
        load_collector_csv(path)

    write_collector_csv(path, [collector_row(0)])
    manifest_path = path.with_name("capacity_run-a_metadata.json")
    manifest_path.write_text(
        '{"run_id":"run-a","run_complete":true,"scenario_id":"scenario-a",'
        '"scenario_type":"constant","output_csv":"capacity_other.csv"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="output_csv"):
        load_collector_csv(path)


def test_targets_generate_all_horizons_and_do_not_use_observed_throughput():
    samples = [sample(seq=i, capacity=100.0 + i) for i in range(36)]

    targets = generate_capacity_targets(samples)
    origin_zero = {
        target.horizon_seconds: target.target_capacity_mbps
        for target in targets
        if target.origin_sample_seq == 0
    }

    assert origin_zero == {5: 105.0, 10: 110.0, 30: 130.0}


def test_targets_do_not_cross_run_boundaries_or_invalid_labels():
    samples = [
        sample(run_id="first", seq=0, elapsed=0),
        sample(run_id="first", seq=1, elapsed=1),
        sample(run_id="second", seq=5, elapsed=5),
        sample(run_id="first", seq=2, elapsed=2, capacity=None),
        sample(run_id="first", seq=5, elapsed=5),
    ]

    targets = generate_capacity_targets(samples, horizons_seconds=(5,))

    assert [(target.run_id, target.target_sample_seq) for target in targets] == [
        ("first", 5)
    ]


def test_targets_match_irregular_timestamps_only_within_tolerance():
    samples = [
        sample(seq=0, elapsed=0),
        sample(seq=1, elapsed=1.0),
        sample(seq=2, elapsed=4.9, capacity=90.0),
        sample(seq=3, elapsed=5.1, capacity=90.0),
        sample(seq=4, elapsed=9.9, capacity=80.0),
        sample(seq=5, elapsed=10.1, capacity=None),
    ]

    close_target = generate_capacity_targets(
        samples, horizons_seconds=(5,), timestamp_tolerance_s=0.2
    )
    missing_target = generate_capacity_targets(
        samples, horizons_seconds=(10,), timestamp_tolerance_s=0.2
    )

    assert close_target[0].target_capacity_mbps == 90.0
    assert missing_target == []


def test_target_is_rejected_when_jitter_brackets_a_capacity_transition():
    samples = [
        sample(seq=0, elapsed=0),
        sample(seq=1, elapsed=4.9, capacity=100.0),
        sample(seq=2, elapsed=5.1, capacity=80.0),
    ]

    assert generate_capacity_targets(
        samples, horizons_seconds=(5,), timestamp_tolerance_s=0.2
    ) == []


def test_features_are_causal_and_include_capacity_and_valid_rates():
    samples = [sample(seq=i, capacity=100 + i, down=2 + i) for i in range(6)]
    features = generate_features(samples)
    by_seq = {row.sample_seq: row.values for row in features}

    assert by_seq[5]["capacity_lag_1"] == 104.0
    assert by_seq[5]["client1_down_mbps_current"] == 7.0
    assert by_seq[5]["aggregate_down_mbps_lag_1"] == 18.0
    assert by_seq[5]["configured_capacity_mbps_change_per_s"] == 1.0
    assert by_seq[5]["configured_capacity_mbps_rolling_mean_5"] == 103.0
    assert tuple(by_seq[5]) == feature_names()

    changed_future = [*samples[:3], sample(seq=3, capacity=9999.0)]
    changed_features = generate_features(changed_future)
    assert changed_features[2].values == features[2].values


def test_features_leave_missing_measurements_missing_and_break_at_sequence_gap():
    samples = [
        sample(seq=0, capacity=100.0, down=None),
        sample(seq=1, capacity=None, down=None),
        sample(seq=3, capacity=90.0, down=None),
    ]

    features = generate_features(samples)
    last = features[-1].values

    assert last["capacity_lag_1"] is None
    assert last["client1_down_mbps_lag_1"] is None
    assert last["aggregate_down_mbps_current"] is None


def test_baselines_are_horizon_specific_and_seasonal_naive_uses_past_only():
    samples = [sample(seq=i, capacity=100 + i) for i in range(15)]
    origin = samples[10]

    assert persistence_forecast(origin) == 110.0
    assert seasonal_naive_forecast(
        samples, origin, horizon_seconds=5, season_seconds=10
    ) == 105.0
    assert seasonal_naive_forecast(
        samples, origin, horizon_seconds=5, season_seconds=3
    ) is None


def test_holt_winters_wrapper_forecasts_and_rejects_insufficient_history():
    model = HoltWintersForecaster(season_length=4).fit(
        [10.0, 12.0, 10.0, 8.0, 10.0, 12.0, 10.0, 8.0]
    )
    assert model.predict_horizon(1) == pytest.approx(10.0, abs=1.0)
    with pytest.raises(ValueError, match="at least 8 observations"):
        HoltWintersForecaster(season_length=4).fit([1.0, 2.0, 3.0])
    with pytest.raises(RuntimeError, match="not fitted"):
        HoltWintersForecaster(season_length=4).predict(1)


def test_holt_winters_fit_samples_stops_at_origin_and_rejects_missing_capacity():
    samples = [sample(seq=i, capacity=100 + i) for i in range(12)]
    origin = samples[7]
    model = HoltWintersForecaster(season_length=3).fit_samples(samples, origin)
    assert model._observation_count == 8
    with pytest.raises(ValueError, match="missing capacity"):
        HoltWintersForecaster(season_length=2).fit_samples(
            [sample(seq=0), sample(seq=1, capacity=None)], sample(seq=1, capacity=None)
        )


def test_lightgbm_missing_dependency_is_explicit(monkeypatch):
    monkeypatch.setitem(sys.modules, "lightgbm", None)
    with pytest.raises(LightGBMDependencyError, match="optional 'lightgbm'"):
        LightGBMForecaster().fit([{"x": 1.0}], [2.0])


def test_lightgbm_wrapper_passes_missing_values_without_zero_imputation(monkeypatch):
    class FakeDataset:
        def __init__(self, matrix, label, feature_name):
            self.matrix = matrix
            self.targets = label
            self.feature_name = feature_name

    class FakeBooster:
        def __init__(self, params, dataset, num_boost_round):
            self.params = params
            self.dataset = dataset
            self.num_boost_round = num_boost_round

        def predict(self, matrix):
            return [row[0] for row in matrix]

        def save_model(self, path):
            self.saved_path = path

    monkeypatch.setitem(
        sys.modules,
        "lightgbm",
        types.SimpleNamespace(
            Dataset=FakeDataset,
            train=lambda params, dataset, num_boost_round: FakeBooster(
                params, dataset, num_boost_round
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "numpy",
        types.SimpleNamespace(asarray=lambda values, dtype: values),
    )
    model = LightGBMForecaster(n_estimators=2).fit(
        [{"x": None}, {"x": 3.0}], [1.0, 3.0]
    )

    assert math.isnan(model._model.dataset.matrix[0][0])
    assert model._model.dataset.matrix[1] == [3.0]
    assert math.isnan(model.predict([{"x": None}])[0])
    model.save_model("model.txt")
    assert model._model.saved_path == "model.txt"


def test_loaded_lightgbm_model_enforces_saved_feature_order(monkeypatch):
    class FakeBooster:
        def feature_name(self):
            return ["first", "second"]

        def predict(self, matrix):
            return [1.0]

    monkeypatch.setitem(
        sys.modules,
        "lightgbm",
        types.SimpleNamespace(Booster=lambda model_file: FakeBooster()),
    )
    model = LightGBMForecaster.from_model_file("model.txt")

    assert model.predict([{"first": 1.0, "second": 2.0}]) == [1.0]
    with pytest.raises(ValueError, match="feature names and order"):
        model.predict([{"second": 2.0, "first": 1.0}])


def make_split_samples(
    *,
    all_test_capacity=None,
    all_validation_capacity=None,
    all_training_constant=False,
):
    scenario_types = [
        "constant",
        "step",
        "periodic",
        "constant",
        "step",
        "periodic",
        "step",
        "periodic",
        "step",
        "periodic",
    ]
    samples = []
    for run_index, scenario_type in enumerate(scenario_types):
        if all_training_constant and run_index < 6:
            scenario_type = "constant"
        capacities = (
            (100.0, 40.0)
            if scenario_type == "step"
            else (80.0, 120.0)
            if scenario_type == "periodic"
            else (100.0, 100.0)
        )
        if run_index >= 8 and all_test_capacity is not None:
            capacities = (all_test_capacity, all_test_capacity)
        if 6 <= run_index < 8 and all_validation_capacity is not None:
            capacities = (all_validation_capacity, all_validation_capacity)
        timestamp = START + timedelta(days=run_index)
        samples.extend(
            (
                sample(
                    run_id=f"run-{run_index}",
                    seq=0,
                    elapsed=0,
                    capacity=capacities[0],
                    scenario_type=scenario_type,
                    timestamp=timestamp,
                ),
                sample(
                    run_id=f"run-{run_index}",
                    seq=1,
                    elapsed=1,
                    capacity=capacities[1],
                    scenario_type=scenario_type,
                    timestamp=timestamp + timedelta(seconds=1),
                ),
            )
        )
    return samples


def test_chronological_split_requires_ten_independent_runs():
    samples = [
        sample(run_id=f"run-{i}", seq=0, timestamp=START + timedelta(days=i))
        for i in range(9)
    ]
    with pytest.raises(ValueError, match="at least 10 independent eligible runs"):
        chronological_run_split(samples)


def test_chronological_split_assigns_whole_runs_and_validates_coverage():
    samples = make_split_samples()
    split = chronological_run_split(samples)
    assert split.train_run_ids == tuple(f"run-{i}" for i in range(6))
    assert split.validation_run_ids == ("run-6", "run-7")
    assert split.test_run_ids == ("run-8", "run-9")
    assert not (set(split.train_run_ids) & set(split.validation_run_ids))
    assert not (set(split.train_run_ids) & set(split.test_run_ids))
    assert not (set(split.validation_run_ids) & set(split.test_run_ids))
    for run_ids in (
        split.train_run_ids,
        split.validation_run_ids,
        split.test_run_ids,
    ):
        assigned_rows = [item for item in samples if item.run_id in run_ids]
        assert {item.run_id for item in assigned_rows} == set(run_ids)
        minimum_scenarios = 3 if run_ids == split.train_run_ids else 1
        assert len({item.scenario_type for item in assigned_rows}) >= minimum_scenarios
    for run_ids in (split.validation_run_ids, split.test_run_ids):
        assigned_rows = [item for item in samples if item.run_id in run_ids]
        assert len({item.configured_capacity_mbps for item in assigned_rows}) >= 2

    metrics = regression_metrics(
        [100.0, 90.0],
        [90.0, 100.0],
        persistence_predicted=[100.0, 100.0],
    )
    assert metrics.count == 2
    assert metrics.mae == 10.0
    assert metrics.rmse == 10.0
    assert metrics.bias == 0.0
    assert metrics.improvement_over_persistence_mae == -1.0


def test_chronological_split_rejects_insufficient_training_scenario_coverage():
    with pytest.raises(ValueError, match="training split requires at least 3 scenario type"):
        chronological_run_split(make_split_samples(all_training_constant=True))


def test_chronological_split_rejects_validation_or_test_without_capacity_variation():
    with pytest.raises(ValueError, match="test split requires at least two valid configured capacity values"):
        chronological_run_split(make_split_samples(all_test_capacity=100.0))
    with pytest.raises(ValueError, match="validation split requires at least two valid configured capacity values"):
        chronological_run_split(make_split_samples(all_validation_capacity=100.0))

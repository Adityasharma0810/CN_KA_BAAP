import csv
import json

import pytest

from experiments.capacity_forecasting.collect_gateway_telemetry import (
    CAPACITY_SOURCE,
    CLIENT_NAMES,
    CSV_FIELDS,
    CapacityReading,
    GatewayTelemetryCollector,
    QdiscReadError,
    calculate_mbps,
    main,
    parse_tbf_capacity,
    read_client_counters,
    read_configured_capacity,
)


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def tbf_json(rate_bytes_per_second=12_500_000):
    return json.dumps(
        [
            {
                "kind": "tbf",
                "handle": "1:",
                "root": True,
                "options": {
                    "rate": rate_bytes_per_second,
                    "burst": 200100,
                    "limit": 625000,
                },
            }
        ]
    )


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def collect(
    path,
    *,
    counters=None,
    capacities=None,
    clock=None,
    duration=1,
    interval=1,
    cadence_tolerance=0.25,
):
    clock = clock or FakeClock()
    counter_calls = {client: 0 for client in CLIENT_NAMES}
    counters = counters or {}
    capacities = capacities or [CapacityReading(100.0, True, CAPACITY_SOURCE)]
    capacity_calls = 0

    def read_counter(client):
        index = counter_calls[client]
        counter_calls[client] += 1
        values = counters.get(client, [(index * 125_000, index * 62_500)])
        if isinstance(values, Exception):
            raise values
        return values[min(index, len(values) - 1)]

    def read_capacity():
        nonlocal capacity_calls
        value = capacities[min(capacity_calls, len(capacities) - 1)]
        capacity_calls += 1
        return value

    collector = GatewayTelemetryCollector(
        counter_reader=read_counter,
        capacity_reader=read_capacity,
        monotonic=clock.monotonic,
        utc_now=lambda: "2026-11-08T12:00:00+00:00",
        sleep=clock.sleep,
    )
    run_id, complete = collector.run(
        path,
        scenario_id="scenario-a",
        scenario_type="constant",
        random_seed=42,
        traffic_profile="idle",
        sample_interval=interval,
        cadence_tolerance=cadence_tolerance,
        duration=duration,
        run_id="run-a",
    )
    return run_id, complete


def test_counter_mapping_uses_bridge_tx_as_download(tmp_path):
    stats = tmp_path / "veth-c1-br" / "statistics"
    stats.mkdir(parents=True)
    (stats / "tx_bytes").write_text("123\n", encoding="ascii")
    (stats / "rx_bytes").write_text("456\n", encoding="ascii")

    assert read_client_counters("client1", tmp_path) == (123, 456)


def test_counter_reader_rejects_unknown_client_and_missing_interface(tmp_path):
    with pytest.raises(ValueError, match="Unknown lab client"):
        read_client_counters("client4", tmp_path)
    with pytest.raises(FileNotFoundError):
        read_client_counters("client1", tmp_path)


def test_calculate_mbps_uses_actual_elapsed_time_and_never_returns_negative():
    assert calculate_mbps(1000, 251_000, 2.0) == 1.0
    assert calculate_mbps(None, 100, 1.0) is None
    assert calculate_mbps(200, 100, 1.0) is None
    assert calculate_mbps(100, 200, 0) is None


def test_first_sample_is_a_counter_baseline_with_missing_rates(tmp_path):
    output = tmp_path / "first.csv"
    _, complete = collect(output, duration=0.1)
    rows = read_rows(output)

    assert complete
    assert len(rows) == 1
    assert rows[0]["sample_seq"] == "0"
    assert rows[0]["sample_interval_s"] == ""
    assert rows[0]["client1_down_mbps"] == ""
    assert rows[0]["client1_up_mbps"] == ""
    assert rows[0]["sample_cadence_valid"] == "False"
    assert rows[0]["sample_cadence_error"] == "first sample has no preceding interval"
    assert rows[0]["run_complete"] == "True"


def test_rates_and_aggregate_rates_use_elapsed_sample_interval(tmp_path):
    output = tmp_path / "rates.csv"
    clock = FakeClock()
    clock.sleep = lambda seconds: setattr(clock, "value", clock.value + 1.25)
    counters = {
        client: [(0, 0), (125_000, 62_500)] for client in CLIENT_NAMES
    }
    collect(
        output,
        counters=counters,
        clock=clock,
        duration=1.25,
        interval=1.0,
        cadence_tolerance=0.2,
    )
    rows = read_rows(output)

    assert float(rows[1]["sample_interval_s"]) == pytest.approx(1.25)
    assert float(rows[1]["client1_down_mbps"]) == pytest.approx(0.8)
    assert float(rows[1]["client1_up_mbps"]) == pytest.approx(0.4)
    assert float(rows[1]["client1_down_rate_interval_s"]) == pytest.approx(1.25)
    assert float(rows[1]["aggregate_down_mbps"]) == pytest.approx(2.4)
    assert rows[1]["sample_cadence_valid"] == "False"


def test_counter_reset_marks_rate_missing_then_rebaselines(tmp_path):
    output = tmp_path / "reset.csv"
    counters = {
        "client1": [(100, 100), (200, 200), (50, 250), (150, 350)]
    }
    collect(output, counters=counters, duration=3)
    rows = read_rows(output)

    assert rows[2]["client1_down_counter_reset"] == "True"
    assert rows[2]["client1_down_mbps"] == ""
    assert rows[2]["client1_up_counter_reset"] == "False"
    assert rows[2]["client1_up_mbps"] != ""
    assert rows[3]["client1_down_counter_reset"] == "False"
    assert float(rows[3]["client1_down_mbps"]) == pytest.approx(0.0008)


def test_missing_interface_is_explicit_and_does_not_become_zero(tmp_path):
    output = tmp_path / "missing.csv"
    counters = {"client2": FileNotFoundError("interface is missing")}
    collect(output, counters=counters, duration=0.1)
    row = read_rows(output)[0]

    assert row["client2_read_valid"] == "False"
    assert "interface is missing" in row["client2_read_error"]
    assert row["client2_down_bytes"] == ""
    assert row["client2_down_mbps"] == ""
    assert row["aggregate_down_mbps"] == ""


def test_invalid_qdisc_does_not_create_capacity_value(tmp_path):
    output = tmp_path / "invalid-qdisc.csv"
    invalid = CapacityReading(
        None, False, CAPACITY_SOURCE, "root qdisc kind is 'noqueue', not 'tbf'"
    )
    collect(output, capacities=[invalid], duration=0.1)
    row = read_rows(output)[0]

    assert row["configured_capacity_mbps"] == ""
    assert row["capacity_config_valid"] == "False"
    assert "noqueue" in row["capacity_read_error"]


def test_tbf_parser_requires_one_valid_root_and_numeric_rate():
    assert parse_tbf_capacity(tbf_json()) == 100.0
    assert parse_tbf_capacity(tbf_json(5_000_000)) == 40.0
    with pytest.raises(QdiscReadError, match="not 'tbf'"):
        parse_tbf_capacity(
            json.dumps([{"kind": "noqueue", "root": True, "options": {}}])
        )
    with pytest.raises(QdiscReadError, match="rate is missing"):
        parse_tbf_capacity(
            json.dumps([{"kind": "tbf", "root": True, "options": {}}])
        )


def test_qdisc_reader_runs_read_only_json_command_and_reports_bad_state():
    class Result:
        returncode = 0
        stdout = json.dumps(
            [{"kind": "noqueue", "root": True, "options": {}}]
        )
        stderr = ""

    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return Result()

    reading = read_configured_capacity(runner=runner)

    assert not reading.valid
    assert reading.capacity_mbps is None
    assert commands[0][0][:4] == ["tc", "-j", "-d", "qdisc"]
    assert commands[0][1]["check"] is False


def test_capacity_changes_are_recorded_only_for_adjacent_valid_samples(tmp_path):
    output = tmp_path / "capacity-change.csv"
    readings = [
        CapacityReading(100.0, True, CAPACITY_SOURCE),
        CapacityReading(100.0, True, CAPACITY_SOURCE),
        CapacityReading(50.0, True, CAPACITY_SOURCE),
    ]
    collect(output, capacities=readings, duration=2)
    rows = read_rows(output)

    assert [row["capacity_changed"] for row in rows] == ["", "False", "True"]
    assert rows[2]["previous_configured_capacity_mbps"] == "100.0"
    assert rows[2]["configured_capacity_mbps"] == "50.0"


def test_csv_schema_metadata_and_success_completeness(tmp_path):
    output = tmp_path / "schema.csv"
    run_id, complete = collect(output, duration=0.1)
    rows = read_rows(output)

    assert complete
    assert run_id == "run-a"
    assert list(rows[0]) == CSV_FIELDS
    assert rows[0]["schema_version"] == "1.1"
    assert rows[0]["scenario_id"] == "scenario-a"
    assert rows[0]["run_id"] == "run-a"
    assert rows[0]["random_seed"] == "42"
    assert rows[0]["scenario_type"] == "constant"
    assert rows[0]["traffic_profile"] == "idle"
    assert rows[0]["timestamp_utc"] == "2026-11-08T12:00:00+00:00"
    assert all(row["run_complete"] == "True" for row in rows)
    assert not any("rtt" in field or "jitter" in field for field in CSV_FIELDS)


def test_interruption_preserves_partial_csv_as_incomplete(tmp_path):
    output = tmp_path / "interrupted.csv"
    clock = FakeClock()

    def interrupt(_seconds):
        raise KeyboardInterrupt

    collector = GatewayTelemetryCollector(
        counter_reader=lambda _client: (100, 200),
        capacity_reader=lambda: CapacityReading(100.0, True, CAPACITY_SOURCE),
        monotonic=clock.monotonic,
        utc_now=lambda: "2026-11-08T12:00:00+00:00",
        sleep=interrupt,
    )
    _, complete = collector.run(
        output,
        scenario_id="scenario-a",
        scenario_type="constant",
        random_seed=None,
        traffic_profile="idle",
        duration=10,
    )
    rows = read_rows(output)

    assert not complete
    assert len(rows) == 1
    assert rows[0]["run_complete"] == "False"
    assert rows[0]["random_seed"] == ""


def test_interruption_before_first_sample_writes_incomplete_status_row(tmp_path):
    output = tmp_path / "interrupted-before-first.csv"
    clock = FakeClock()

    def interrupt_before_read():
        raise KeyboardInterrupt

    collector = GatewayTelemetryCollector(
        counter_reader=lambda _client: (100, 200),
        capacity_reader=interrupt_before_read,
        monotonic=clock.monotonic,
        utc_now=lambda: "2026-11-08T12:00:00+00:00",
        sleep=clock.sleep,
    )
    _, complete = collector.run(
        output,
        scenario_id="scenario-a",
        scenario_type="constant",
        random_seed=None,
        traffic_profile="idle",
        duration=10,
    )
    rows = read_rows(output)

    assert not complete
    assert len(rows) == 1
    assert rows[0]["run_complete"] == "False"
    assert rows[0]["capacity_config_valid"] == "False"
    assert rows[0]["client1_read_valid"] == "False"
    assert rows[0]["client1_read_error"]


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "existing.csv"
    output.write_text("keep me\n", encoding="utf-8")
    collector = GatewayTelemetryCollector()

    with pytest.raises(FileExistsError):
        collector.run(
            output,
            scenario_id="scenario-a",
            scenario_type="constant",
            random_seed=None,
            traffic_profile="idle",
            duration=1,
        )
    assert output.read_text(encoding="utf-8") == "keep me\n"


def test_deadline_schedule_does_not_accumulate_sample_work_time(tmp_path):
    clock = FakeClock()

    def slow_counter(_client):
        clock.value += 0.05
        return (int(clock.value * 125_000), int(clock.value * 62_500))

    def slow_capacity():
        clock.value += 0.2
        return CapacityReading(100.0, True, CAPACITY_SOURCE)

    collector = GatewayTelemetryCollector(
        counter_reader=slow_counter,
        capacity_reader=slow_capacity,
        monotonic=clock.monotonic,
        utc_now=lambda: "2026-11-08T12:00:00+00:00",
        sleep=clock.sleep,
    )
    output = tmp_path / "deadline.csv"
    collector.run(
        output,
        scenario_id="scenario-a",
        scenario_type="constant",
        random_seed=42,
        traffic_profile="idle",
        sample_interval=1.0,
        cadence_tolerance=0.25,
        duration=3.0,
        run_id="deadline-run",
    )
    rows = read_rows(output)

    assert len(rows) == 4
    assert [float(row["sample_interval_s"]) for row in rows[1:]] == pytest.approx(
        [1.0, 1.0, 1.0]
    )
    assert [row["sample_cadence_valid"] for row in rows] == [
        "False",
        "True",
        "True",
        "True",
    ]


def test_delayed_sample_skips_missed_deadlines_and_marks_cadence_invalid(tmp_path):
    clock = FakeClock()

    delays = iter((0.1, 1.4))

    def slow_capacity():
        clock.value += next(delays, 0.1)
        return CapacityReading(100.0, True, CAPACITY_SOURCE)

    collector = GatewayTelemetryCollector(
        counter_reader=lambda _client: (int(clock.value * 125_000), 0),
        capacity_reader=slow_capacity,
        monotonic=clock.monotonic,
        utc_now=lambda: "2026-11-08T12:00:00+00:00",
        sleep=clock.sleep,
    )
    output = tmp_path / "delayed.csv"
    collector.run(
        output,
        scenario_id="scenario-a",
        scenario_type="constant",
        random_seed=42,
        traffic_profile="idle",
        sample_interval=1.0,
        cadence_tolerance=0.25,
        duration=2.5,
        run_id="delayed-run",
    )
    rows = read_rows(output)

    assert len(rows) == 2
    assert float(rows[1]["sample_interval_s"]) == pytest.approx(2.3)
    assert rows[1]["sample_cadence_valid"] == "False"
    assert "outside 1.0s +/- 0.25s" in rows[1]["sample_cadence_error"]
    assert rows[0]["sample_seq"] == "0"
    assert rows[1]["sample_seq"] == "1"


def test_explicit_run_id_is_logged_and_written_to_every_row(tmp_path, monkeypatch, capsys):
    path = tmp_path / "capacity_shared-run.csv"
    output_id = "shared-run"
    observed = {}

    class FakeCollector:
        def run(self, output_path, **kwargs):
            observed["output_path"] = output_path
            observed.update(kwargs)
            output_path.write_text("test output\n", encoding="utf-8")
            return kwargs["run_id"], True

    monkeypatch.setattr(
        "experiments.capacity_forecasting.collect_gateway_telemetry.GatewayTelemetryCollector",
        FakeCollector,
    )
    result = main(
        [
            "--output-file",
            str(path),
            "--scenario-id",
            "scenario-a",
            "--scenario-type",
            "constant",
            "--traffic-profile",
            "test",
            "--run-id",
            output_id,
            "--duration",
            "1",
        ]
    )

    assert result == 0
    assert observed["run_id"] == output_id
    assert observed["output_path"] == path
    assert output_id in str(path)
    assert f"run_id={output_id}" in capsys.readouterr().out

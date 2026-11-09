#!/usr/bin/env python3
"""Collect timestamped gateway counters and verified shared TBF capacity."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = "1.1"
CLIENT_NAMES = ("client1", "client2", "client3")
BRIDGE_NAME = "br-lab"
TC_JSON_COMMAND = ("tc", "-j", "-d", "qdisc", "show", "dev", BRIDGE_NAME)
DEFAULT_SAMPLE_INTERVAL = 1.0
DEFAULT_CADENCE_TOLERANCE = 0.25
DEFAULT_DURATION = 60.0
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "capacity_forecasting" / "raw"
)
CAPACITY_SOURCE = "tc -j -d qdisc show dev br-lab; root TBF options.rate"

BASE_FIELDS = (
    "schema_version",
    "scenario_id",
    "run_id",
    "random_seed",
    "scenario_type",
    "traffic_profile",
    "sample_seq",
    "timestamp_utc",
    "elapsed_s",
    "sample_interval_s",
    "sample_interval_target_s",
    "sample_cadence_tolerance_s",
    "sample_cadence_valid",
    "sample_cadence_error",
    "configured_capacity_mbps",
    "capacity_config_source",
    "capacity_config_valid",
    "capacity_read_error",
    "previous_configured_capacity_mbps",
    "capacity_changed",
    "sample_timing_valid",
    "sample_timing_error",
)


def csv_fields() -> list[str]:
    fields = list(BASE_FIELDS)
    for client in CLIENT_NAMES:
        fields.extend(
            (
                f"{client}_down_bytes",
                f"{client}_up_bytes",
                f"{client}_down_mbps",
                f"{client}_up_mbps",
                f"{client}_down_rate_interval_s",
                f"{client}_up_rate_interval_s",
                f"{client}_down_counter_reset",
                f"{client}_up_counter_reset",
                f"{client}_read_valid",
                f"{client}_read_error",
            )
        )
    fields.extend(("aggregate_down_mbps", "aggregate_up_mbps", "run_complete"))
    return fields


CSV_FIELDS = csv_fields()


class QdiscReadError(ValueError):
    """The active bridge root qdisc does not verify a usable TBF capacity."""


@dataclass(frozen=True)
class CapacityReading:
    capacity_mbps: float | None
    valid: bool
    source: str
    error: str | None = None


def read_client_counters(
    client: str, sys_class_net: Path = Path("/sys/class/net")
) -> tuple[int, int]:
    """Return (download_bytes, upload_bytes) from the bridge-side veth.

    The bridge transmits bytes that the client downloads; it receives bytes
    that the client uploads.
    """
    if client not in CLIENT_NAMES:
        raise ValueError(f"Unknown lab client: {client}")

    statistics = sys_class_net / f"veth-c{client[-1]}-br" / "statistics"
    down_bytes = _read_counter(statistics / "tx_bytes")
    up_bytes = _read_counter(statistics / "rx_bytes")
    return down_bytes, up_bytes


def _read_counter(path: Path) -> int:
    value = int(path.read_text(encoding="ascii").strip())
    if value < 0:
        raise ValueError(f"Counter must be non-negative: {path}")
    return value


def calculate_mbps(
    previous_bytes: int | None, current_bytes: int, elapsed_seconds: float
) -> float | None:
    """Calculate a non-negative Mbit/s rate, or None without a valid baseline."""
    if previous_bytes is None:
        return None
    if current_bytes < previous_bytes:
        return None
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        return None
    return (current_bytes - previous_bytes) * 8 / elapsed_seconds / 1_000_000


def parse_tbf_capacity(output: str) -> float:
    """Parse iproute2 JSON and return the verified root TBF rate in Mbit/s.

    The numeric TBF options.rate value from ``tc -j`` is bytes per second.
    The parser converts it to decimal Mbit/s and is intentionally strict:
    absent, ambiguous, malformed, or non-TBF qdiscs are not capacity.
    """
    try:
        qdiscs = json.loads(output)
    except json.JSONDecodeError as error:
        raise QdiscReadError(f"invalid tc JSON: {error.msg}") from error

    if not isinstance(qdiscs, list):
        raise QdiscReadError("tc JSON must be a list of qdisc objects")

    roots = [
        qdisc
        for qdisc in qdiscs
        if isinstance(qdisc, dict) and qdisc.get("root") is True
    ]
    if len(roots) != 1:
        raise QdiscReadError(
            f"expected exactly one root qdisc on {BRIDGE_NAME}; found {len(roots)}"
        )

    root = roots[0]
    if root.get("kind") != "tbf":
        raise QdiscReadError(
            f"root qdisc kind is {root.get('kind')!r}, not 'tbf'"
        )

    options = root.get("options")
    if not isinstance(options, dict):
        raise QdiscReadError("root TBF qdisc has no options object")

    rate_bytes_per_second = options.get("rate")
    if (
        isinstance(rate_bytes_per_second, bool)
        or not isinstance(rate_bytes_per_second, (int, float))
        or not math.isfinite(rate_bytes_per_second)
        or rate_bytes_per_second <= 0
    ):
        raise QdiscReadError("root TBF options.rate is missing or invalid")

    return float(rate_bytes_per_second) * 8 / 1_000_000


def read_configured_capacity(
    runner: Callable = subprocess.run,
) -> CapacityReading:
    """Read the active root TBF state without changing qdisc configuration."""
    try:
        result = runner(
            list(TC_JSON_COMMAND),
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or f"tc exited with {result.returncode}"
            raise QdiscReadError(detail)
        capacity = parse_tbf_capacity(result.stdout)
        return CapacityReading(capacity, True, CAPACITY_SOURCE)
    except (OSError, subprocess.SubprocessError, QdiscReadError) as error:
        return CapacityReading(None, False, CAPACITY_SOURCE, str(error))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_float(value: float | None) -> float | str:
    return "" if value is None else value


def _optional_rate(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


class GatewayTelemetryCollector:
    """Append one run of samples; this class does not launch or shape traffic."""

    def __init__(
        self,
        counter_reader: Callable[[str], tuple[int, int]] = read_client_counters,
        capacity_reader: Callable[[], CapacityReading] = read_configured_capacity,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], str] = _utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.counter_reader = counter_reader
        self.capacity_reader = capacity_reader
        self.monotonic = monotonic
        self.utc_now = utc_now
        self.sleep = sleep
        self._counter_baselines: dict[str, dict[str, tuple[int, float] | None]] = {
            client: {"down": None, "up": None} for client in CLIENT_NAMES
        }
        self._previous_sample_capacity: float | None = None
        self._previous_sample_valid = False

    def run(
        self,
        output_path: Path,
        *,
        scenario_id: str,
        scenario_type: str,
        random_seed: int | None,
        traffic_profile: str,
        sample_interval: float = DEFAULT_SAMPLE_INTERVAL,
        cadence_tolerance: float = DEFAULT_CADENCE_TOLERANCE,
        duration: float = DEFAULT_DURATION,
        run_id: str | None = None,
    ) -> tuple[str, bool]:
        _validate_run_parameters(sample_interval, duration, cadence_tolerance)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        run_id = run_id or str(uuid.uuid4())
        start = self.monotonic()
        previous_sample_time: float | None = None
        sample_seq = 0
        next_deadline = start
        end_deadline = start + duration
        complete = False

        # Exclusive creation prevents accidental replacement of existing data.
        with output_path.open("x", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS)
            writer.writeheader()
            output_file.flush()

            try:
                while next_deadline <= end_deadline:
                    delay = next_deadline - self.monotonic()
                    if delay > 0:
                        self.sleep(delay)
                    row, sample_time = self._sample(
                        scenario_id=scenario_id,
                        run_id=run_id,
                        random_seed=random_seed,
                        scenario_type=scenario_type,
                        traffic_profile=traffic_profile,
                        sample_seq=sample_seq,
                        start_time=start,
                        previous_sample_time=previous_sample_time,
                        nominal_sample_interval=sample_interval,
                        cadence_tolerance=cadence_tolerance,
                    )
                    writer.writerow(row)
                    output_file.flush()
                    os.fsync(output_file.fileno())
                    previous_sample_time = sample_time
                    sample_seq += 1
                    next_deadline += sample_interval
                    now = self.monotonic()
                    if next_deadline <= now:
                        missed_deadlines = (
                            math.floor((now - next_deadline) / sample_interval) + 1
                        )
                        next_deadline += missed_deadlines * sample_interval
                complete = True
            except KeyboardInterrupt:
                complete = False
                if sample_seq == 0:
                    writer.writerow(
                        _interrupted_row(
                            scenario_id=scenario_id,
                            run_id=run_id,
                            random_seed=random_seed,
                            scenario_type=scenario_type,
                            traffic_profile=traffic_profile,
                            timestamp_utc=self.utc_now(),
                            elapsed_s=self.monotonic() - start,
                        )
                    )
            finally:
                output_file.flush()
                os.fsync(output_file.fileno())

        if complete:
            _mark_run_complete(output_path)
        return run_id, complete

    def _sample(
        self,
        *,
        scenario_id: str,
        run_id: str,
        random_seed: int | None,
        scenario_type: str,
        traffic_profile: str,
        sample_seq: int,
        start_time: float,
        previous_sample_time: float | None,
        nominal_sample_interval: float,
        cadence_tolerance: float,
    ) -> tuple[dict[str, object], float]:
        capacity = self.capacity_reader()
        capacity_valid = (
            capacity.valid
            and capacity.capacity_mbps is not None
            and math.isfinite(capacity.capacity_mbps)
            and capacity.capacity_mbps > 0
        )
        capacity_value = capacity.capacity_mbps if capacity_valid else None
        capacity_error = capacity.error or ""
        if capacity.valid and not capacity_valid and not capacity_error:
            capacity_error = "capacity reader returned an invalid rate"
        capacity_changed: bool | str
        previous_capacity: float | str
        if capacity_valid and self._previous_sample_valid:
            previous_capacity = (
                self._previous_sample_capacity
                if self._previous_sample_capacity is not None
                else ""
            )
            capacity_changed = capacity_value != self._previous_sample_capacity
        else:
            previous_capacity = ""
            capacity_changed = ""
        self._previous_sample_capacity = capacity_value
        self._previous_sample_valid = capacity_valid

        row: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "scenario_id": scenario_id,
            "run_id": run_id,
            "random_seed": "" if random_seed is None else random_seed,
            "scenario_type": scenario_type,
            "traffic_profile": traffic_profile,
            "sample_seq": sample_seq,
            "configured_capacity_mbps": _format_float(capacity_value),
            "capacity_config_source": capacity.source,
            "capacity_config_valid": capacity_valid,
            "capacity_read_error": capacity_error,
            "previous_configured_capacity_mbps": _format_float(previous_capacity),
            "capacity_changed": capacity_changed,
            "run_complete": False,
        }

        client_rates: dict[str, dict[str, float | None]] = {}
        for client in CLIENT_NAMES:
            client_row = self._sample_client(client)
            row.update(client_row)
            client_rates[client] = {
                "down": _optional_rate(client_row[f"{client}_down_mbps"]),
                "up": _optional_rate(client_row[f"{client}_up_mbps"]),
            }

        for direction in ("down", "up"):
            rates = [client_rates[client][direction] for client in CLIENT_NAMES]
            row[f"aggregate_{direction}_mbps"] = (
                sum(rates) if all(rate is not None for rate in rates) else ""
            )
        sample_time = self.monotonic()
        timing_valid = math.isfinite(sample_time - start_time) and sample_time >= start_time
        elapsed = sample_time - start_time if timing_valid else None
        sample_interval = (
            sample_time - previous_sample_time
            if previous_sample_time is not None
            else None
        )
        timing_error = ""
        if previous_sample_time is not None and (
            sample_interval is None
            or not math.isfinite(sample_interval)
            or sample_interval <= 0
        ):
            timing_valid = False
            sample_interval = None
            timing_error = "monotonic sample interval was not positive and finite"
        cadence_valid = (
            timing_valid
            and sample_interval is not None
            and abs(sample_interval - nominal_sample_interval) <= cadence_tolerance
        )
        if previous_sample_time is None:
            cadence_error = "first sample has no preceding interval"
        elif not cadence_valid:
            cadence_error = (
                f"interval {sample_interval!r}s is outside "
                f"{nominal_sample_interval}s +/- {cadence_tolerance}s"
            )
        else:
            cadence_error = ""
        row.update(
            {
                "timestamp_utc": self.utc_now(),
                "elapsed_s": _format_float(elapsed),
                "sample_interval_s": _format_float(sample_interval),
                "sample_timing_valid": timing_valid,
                "sample_timing_error": timing_error,
                "sample_interval_target_s": nominal_sample_interval,
                "sample_cadence_tolerance_s": cadence_tolerance,
                "sample_cadence_valid": cadence_valid,
                "sample_cadence_error": cadence_error,
            }
        )
        return row, sample_time

    def _sample_client(self, client: str) -> dict[str, object]:
        prefix = f"{client}_"
        row: dict[str, object] = {
            f"{prefix}down_bytes": "",
            f"{prefix}up_bytes": "",
            f"{prefix}down_mbps": "",
            f"{prefix}up_mbps": "",
            f"{prefix}down_rate_interval_s": "",
            f"{prefix}up_rate_interval_s": "",
            f"{prefix}down_counter_reset": False,
            f"{prefix}up_counter_reset": False,
            f"{prefix}read_valid": False,
            f"{prefix}read_error": "",
        }
        try:
            down_bytes, up_bytes = self.counter_reader(client)
            if (
                isinstance(down_bytes, bool)
                or not isinstance(down_bytes, int)
                or down_bytes < 0
                or isinstance(up_bytes, bool)
                or not isinstance(up_bytes, int)
                or up_bytes < 0
            ):
                raise ValueError("counter values must be non-negative integers")
        except (OSError, ValueError) as error:
            row[f"{prefix}read_error"] = str(error)
            return row

        sample_time = self.monotonic()
        row[f"{prefix}down_bytes"] = down_bytes
        row[f"{prefix}up_bytes"] = up_bytes
        row[f"{prefix}read_valid"] = True

        for direction, current in (("down", down_bytes), ("up", up_bytes)):
            baseline = self._counter_baselines[client][direction]
            if baseline is None:
                self._counter_baselines[client][direction] = (current, sample_time)
                continue

            previous, previous_time = baseline
            interval = sample_time - previous_time
            rate = calculate_mbps(previous, current, interval)
            if current < previous:
                row[f"{prefix}{direction}_counter_reset"] = True
                self._counter_baselines[client][direction] = (current, sample_time)
            elif rate is not None:
                row[f"{prefix}{direction}_mbps"] = rate
                row[f"{prefix}{direction}_rate_interval_s"] = interval
                self._counter_baselines[client][direction] = (current, sample_time)

        return row


def _validate_run_parameters(
    sample_interval: float, duration: float, cadence_tolerance: float
) -> None:
    if not math.isfinite(sample_interval) or sample_interval <= 0:
        raise ValueError("sampling interval must be a positive finite number")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be a positive finite number")
    if not math.isfinite(cadence_tolerance) or cadence_tolerance < 0:
        raise ValueError("cadence tolerance must be a non-negative finite number")


def _interrupted_row(
    *,
    scenario_id: str,
    run_id: str,
    random_seed: int | None,
    scenario_type: str,
    traffic_profile: str,
    timestamp_utc: str,
    elapsed_s: float,
) -> dict[str, object]:
    row: dict[str, object] = {field: "" for field in CSV_FIELDS}
    row.update(
        {
            "schema_version": SCHEMA_VERSION,
            "scenario_id": scenario_id,
            "run_id": run_id,
            "random_seed": "" if random_seed is None else random_seed,
            "scenario_type": scenario_type,
            "traffic_profile": traffic_profile,
            "sample_seq": 0,
            "timestamp_utc": timestamp_utc,
            "elapsed_s": elapsed_s if math.isfinite(elapsed_s) and elapsed_s >= 0 else "",
            "sample_interval_target_s": "",
            "sample_cadence_tolerance_s": "",
            "sample_cadence_valid": False,
            "sample_cadence_error": "sampling interrupted before sample completed",
            "capacity_config_source": CAPACITY_SOURCE,
            "capacity_config_valid": False,
            "capacity_read_error": "sampling interrupted before sample completed",
            "sample_timing_valid": False,
            "sample_timing_error": "sampling interrupted before sample completed",
            "run_complete": False,
        }
    )
    for client in CLIENT_NAMES:
        row[f"{client}_read_valid"] = False
        row[f"{client}_read_error"] = "sampling interrupted before sample completed"
    return row


def _mark_run_complete(output_path: Path) -> None:
    """Mark all rows complete after successful collection, preserving atomicity."""
    temporary_path = output_path.with_name(
        f".{output_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with output_path.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            with temporary_path.open("x", newline="", encoding="utf-8") as target:
                writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
                writer.writeheader()
                for row in reader:
                    row["run_complete"] = "True"
                    writer.writerow(row)
                target.flush()
                os.fsync(target.fileno())
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _resolve_output_path(output: Path, run_id: str) -> Path:
    output = Path(output)
    if output.suffix.lower() == ".csv":
        return output
    return output / f"gateway_telemetry_{run_id}.csv"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record gateway counter telemetry and verified root TBF capacity."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--output-file",
        type=Path,
        help="optional exact CSV path; it must not already exist",
    )
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--scenario-type", required=True)
    parser.add_argument("--random-seed", "--seed", type=int)
    parser.add_argument(
        "--run-id",
        help="optional run ID supplied by an experiment orchestrator",
    )
    parser.add_argument("--traffic-profile", required=True)
    parser.add_argument(
        "--sampling-interval",
        type=float,
        default=DEFAULT_SAMPLE_INTERVAL,
        help="nominal seconds between samples (default: 1)",
    )
    parser.add_argument(
        "--sampling-tolerance",
        type=float,
        default=DEFAULT_CADENCE_TOLERANCE,
        help=(
            "maximum absolute deviation in seconds for a cadence-valid sample "
            f"(default: {DEFAULT_CADENCE_TOLERANCE})"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help="collection duration in seconds (default: 60)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        _validate_run_parameters(
            args.sampling_interval, args.duration, args.sampling_tolerance
        )
    except ValueError as error:
        parser.error(str(error))

    run_id = args.run_id or str(uuid.uuid4())
    output_path = args.output_file or _resolve_output_path(args.output_dir, run_id)
    collector = GatewayTelemetryCollector()
    try:
        run_id, complete = collector.run(
            output_path,
            scenario_id=args.scenario_id,
            scenario_type=args.scenario_type,
            random_seed=args.random_seed,
            traffic_profile=args.traffic_profile,
            sample_interval=args.sampling_interval,
            cadence_tolerance=args.sampling_tolerance,
            duration=args.duration,
            run_id=run_id,
        )
    except FileExistsError:
        print(f"Refusing to overwrite existing output: {output_path}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"Could not write telemetry output {output_path}: {error}", file=sys.stderr)
        return 2

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    print(f"run_complete={str(complete).lower()}")
    return 0 if complete else 130


if __name__ == "__main__":
    raise SystemExit(main())

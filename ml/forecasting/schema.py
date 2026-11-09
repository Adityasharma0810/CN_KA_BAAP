"""Validation and loading for collector-produced capacity telemetry CSVs."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = "1.1"
SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1"}
CLIENT_NAMES = ("client1", "client2", "client3")
CADENCE_FIELDS = {
    "sample_interval_target_s",
    "sample_cadence_tolerance_s",
    "sample_cadence_valid",
    "sample_cadence_error",
}
REQUIRED_FIELDS = {
    "schema_version",
    "scenario_id",
    "scenario_type",
    "run_id",
    "sample_seq",
    "timestamp_utc",
    "elapsed_s",
    "sample_interval_s",
    "configured_capacity_mbps",
    "capacity_config_valid",
    "sample_timing_valid",
    "run_complete",
    "aggregate_down_mbps",
    "aggregate_up_mbps",
    *(f"{client}_{field}" for client in CLIENT_NAMES for field in (
        "down_mbps",
        "up_mbps",
        "read_valid",
        "down_counter_reset",
        "up_counter_reset",
    )),
}


@dataclass(frozen=True)
class TelemetrySample:
    """One validated collector row; missing measurements remain ``None``."""

    schema_version: str
    scenario_id: str
    run_id: str
    sample_seq: int
    timestamp_utc: datetime
    elapsed_s: float
    sample_interval_s: float | None
    configured_capacity_mbps: float | None
    capacity_config_valid: bool
    sample_timing_valid: bool
    client_rates_mbps: dict[str, dict[str, float | None]]
    aggregate_rates_mbps: dict[str, float | None]
    sample_interval_target_s: float | None = None
    sample_cadence_tolerance_s: float | None = None
    sample_cadence_valid: bool = False
    scenario_type: str = "unknown"


def _parse_bool(value: str, column: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{column} must be True or False, got {value!r}")


def _parse_optional_number(value: str) -> float | None:
    if not value.strip():
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _read_rate(row: dict[str, str], column: str, usable: bool) -> float | None:
    value = _parse_optional_number(row[column])
    if not usable or value is None or value < 0:
        return None
    return value


def load_collector_csv(path: str | Path) -> list[TelemetrySample]:
    """Load one complete schema-v1 collector run without imputing values.

    Invalid capacity observations are retained as timestamped rows with a
    missing target, so target alignment cannot jump across an invalid sample.
    Incomplete runs are rejected in full.
    """
    file_path = Path(path)
    if not file_path.name.startswith("capacity_") or file_path.suffix != ".csv":
        raise ValueError(
            f"{file_path}: collector CSV filename must be capacity_<run_id>.csv"
        )
    filename_run_id = file_path.stem.removeprefix("capacity_")
    if not filename_run_id:
        raise ValueError(f"{file_path}: collector CSV filename has an empty run ID")
    manifest_path = file_path.with_name(f"{file_path.stem}_metadata.json")
    if not manifest_path.is_file():
        raise ValueError(f"{file_path}: matching metadata manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"{manifest_path}: could not read matching metadata manifest: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise ValueError(f"{manifest_path}: metadata manifest must contain a JSON object")
    manifest_run_id = manifest.get("run_id")
    if manifest_run_id != filename_run_id:
        raise ValueError(
            f"{manifest_path}: manifest run_id {manifest_run_id!r} does not match "
            f"CSV filename run_id {filename_run_id!r}"
        )
    if manifest.get("run_complete") is not True:
        raise ValueError(f"{manifest_path}: manifest does not mark the run complete")
    manifest_csv = manifest.get("output_csv")
    if manifest_csv is not None and Path(str(manifest_csv)).name != file_path.name:
        raise ValueError(
            f"{manifest_path}: output_csv {manifest_csv!r} does not match "
            f"CSV filename {file_path.name!r}"
        )

    with file_path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"{file_path}: CSV has no header")
        missing_fields = REQUIRED_FIELDS.difference(reader.fieldnames)
        if missing_fields:
            raise ValueError(
                f"{file_path}: missing required columns: "
                f"{', '.join(sorted(missing_fields))}"
            )
        rows = list(reader)

    if not rows:
        raise ValueError(f"{file_path}: CSV contains no samples")

    if manifest.get("scenario_id") != rows[0].get("scenario_id"):
        raise ValueError(
            f"{manifest_path}: manifest scenario_id does not match CSV rows"
        )
    if manifest.get("scenario_type") != rows[0].get("scenario_type"):
        raise ValueError(
            f"{manifest_path}: manifest scenario_type does not match CSV rows"
        )

    samples: list[TelemetrySample] = []
    expected_run_id = filename_run_id
    previous_seq = -1
    previous_elapsed = -math.inf

    for row_number, row in enumerate(rows, start=2):
        prefix = f"{file_path}:{row_number}"
        if row["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"{prefix}: unsupported schema_version {row['schema_version']!r}"
            )
        if row["schema_version"] == "1.1" and not CADENCE_FIELDS.issubset(
            reader.fieldnames or ()
        ):
            raise ValueError(f"{prefix}: schema 1.1 requires cadence columns")
        run_id = row["run_id"].strip()
        if not run_id:
            raise ValueError(f"{prefix}: run_id is empty")
        if run_id != expected_run_id:
            raise ValueError(
                f"{prefix}: row run_id {run_id!r} does not match CSV filename "
                f"run_id {expected_run_id!r}"
            )
        if row["scenario_id"] != manifest.get("scenario_id"):
            raise ValueError(f"{prefix}: scenario_id does not match metadata manifest")
        if row["scenario_type"] != manifest.get("scenario_type"):
            raise ValueError(f"{prefix}: scenario_type does not match metadata manifest")
        if not _parse_bool(row["run_complete"], "run_complete"):
            raise ValueError(f"{prefix}: incomplete runs cannot be loaded")

        try:
            sample_seq = int(row["sample_seq"])
            elapsed_s = float(row["elapsed_s"])
            timestamp = datetime.fromisoformat(row["timestamp_utc"])
        except (ValueError, TypeError) as error:
            raise ValueError(f"{prefix}: invalid sequence or timestamp") from error
        if sample_seq <= previous_seq:
            raise ValueError(f"{prefix}: sample_seq must strictly increase")
        if not math.isfinite(elapsed_s) or elapsed_s <= previous_elapsed:
            raise ValueError(f"{prefix}: elapsed_s must be finite and strictly increasing")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError(f"{prefix}: timestamp_utc must include a timezone")
        previous_seq = sample_seq
        previous_elapsed = elapsed_s

        timing_valid = _parse_bool(row["sample_timing_valid"], "sample_timing_valid")
        capacity_flag = _parse_bool(
            row["capacity_config_valid"], "capacity_config_valid"
        )
        capacity = _parse_optional_number(row["configured_capacity_mbps"])
        capacity_valid = capacity_flag and capacity is not None and capacity > 0
        if not capacity_valid:
            capacity = None

        interval = _parse_optional_number(row["sample_interval_s"])
        if interval is not None and interval <= 0:
            interval = None

        if row["schema_version"] == "1.1":
            nominal_interval = _parse_optional_number(
                row["sample_interval_target_s"]
            )
            cadence_tolerance = _parse_optional_number(
                row["sample_cadence_tolerance_s"]
            )
            cadence_flag = _parse_bool(
                row["sample_cadence_valid"], "sample_cadence_valid"
            )
            cadence_valid = (
                cadence_flag
                and timing_valid
                and interval is not None
                and nominal_interval is not None
                and nominal_interval > 0
                and cadence_tolerance is not None
                and cadence_tolerance >= 0
                and abs(interval - nominal_interval) <= cadence_tolerance
            )
        else:
            # Legacy 1.0 files do not say what cadence they targeted. Preserve
            # their values, but never treat them as a verified regular grid.
            nominal_interval = None
            cadence_tolerance = None
            cadence_valid = False

        client_rates: dict[str, dict[str, float | None]] = {}
        for client in CLIENT_NAMES:
            read_valid = _parse_bool(row[f"{client}_read_valid"], f"{client}_read_valid")
            down_reset = _parse_bool(
                row[f"{client}_down_counter_reset"],
                f"{client}_down_counter_reset",
            )
            up_reset = _parse_bool(
                row[f"{client}_up_counter_reset"],
                f"{client}_up_counter_reset",
            )
            client_rates[client] = {
                "down": _read_rate(
                    row, f"{client}_down_mbps", read_valid and timing_valid and not down_reset
                ),
                "up": _read_rate(
                    row, f"{client}_up_mbps", read_valid and timing_valid and not up_reset
                ),
            }

        aggregate_rates: dict[str, float | None] = {}
        for direction in ("down", "up"):
            client_values = [
                client_rates[client][direction] for client in CLIENT_NAMES
            ]
            aggregate = _read_rate(
                row,
                f"aggregate_{direction}_mbps",
                timing_valid and all(value is not None for value in client_values),
            )
            if aggregate is not None and not math.isclose(
                aggregate,
                sum(value for value in client_values if value is not None),
                rel_tol=1e-6,
                abs_tol=1e-6,
            ):
                aggregate = None
            aggregate_rates[direction] = aggregate

        samples.append(
            TelemetrySample(
                schema_version=SCHEMA_VERSION,
                scenario_id=row["scenario_id"],
                scenario_type=row["scenario_type"],
                run_id=run_id,
                sample_seq=sample_seq,
                timestamp_utc=timestamp,
                elapsed_s=elapsed_s,
                sample_interval_s=interval,
                sample_interval_target_s=nominal_interval,
                sample_cadence_tolerance_s=cadence_tolerance,
                sample_cadence_valid=cadence_valid,
                configured_capacity_mbps=capacity,
                capacity_config_valid=capacity_valid,
                sample_timing_valid=timing_valid,
                client_rates_mbps=client_rates,
                aggregate_rates_mbps=aggregate_rates,
            )
        )

    return samples


def load_collector_csvs(paths: list[str | Path]) -> list[TelemetrySample]:
    """Load multiple independent run files, rejecting duplicate run IDs."""
    samples: list[TelemetrySample] = []
    seen_run_ids: set[str] = set()
    for path in paths:
        run_samples = load_collector_csv(path)
        run_id = run_samples[0].run_id
        if run_id in seen_run_ids:
            raise ValueError(f"duplicate run_id across files: {run_id}")
        seen_run_ids.add(run_id)
        samples.extend(run_samples)
    return samples

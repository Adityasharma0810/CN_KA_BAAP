import sqlite3
from pathlib import Path

import pytest

from network.telemetry.metrics_store import (
    CorruptDatabaseError,
    MetricsStore,
    MigrationError,
    SCHEMA_VERSION,
)


LEGACY_SCHEMA = """
CREATE TABLE network_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    interface_label TEXT NOT NULL,
    download_mbps REAL,
    upload_mbps REAL,
    adapter_up INTEGER,
    internet_reachable INTEGER,
    probe_target TEXT,
    probes_sent INTEGER,
    probes_received INTEGER,
    packet_loss_percent REAL,
    rtt_min_ms REAL,
    rtt_avg_ms REAL,
    rtt_max_ms REAL,
    rtt_jitter_avg_ms REAL
);

CREATE INDEX idx_network_samples_recorded_at
    ON network_samples(recorded_at);
"""


def create_legacy_database(path: Path, rows=()):
    connection = sqlite3.connect(path)

    try:
        connection.executescript(LEGACY_SCHEMA)
        connection.executemany(
            """
            INSERT INTO network_samples (
                recorded_at,
                interface_label,
                download_mbps,
                upload_mbps,
                adapter_up,
                internet_reachable,
                probe_target,
                probes_sent,
                probes_received,
                packet_loss_percent,
                rtt_min_ms,
                rtt_avg_ms,
                rtt_max_ms,
                rtt_jitter_avg_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()

    finally:
        connection.close()


def legacy_rows():
    return (
        (
            "2026-11-09T12:00:00+00:00",
            "Wi-Fi",
            12.5,
            2.5,
            1,
            1,
            "1.1.1.1",
            10,
            9,
            10.0,
            10.0,
            15.0,
            20.0,
            2.5,
        ),
        (
            "2026-11-09T12:00:01+00:00",
            "hotspot-aggregate",
            4.0,
            1.0,
            1,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    )


def canonical_rows(path: Path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row

    try:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM telemetry_observations ORDER BY id"
            ).fetchall()
        ]

    finally:
        connection.close()


def test_missing_database_is_created_at_current_version(tmp_path):
    path = tmp_path / "new.sqlite3"
    store = MetricsStore(path)

    assert store.schema_version() == SCHEMA_VERSION
    assert store.count_samples() == 0
    assert canonical_rows(path) == []


def test_legacy_rows_survive_and_advance_schema_version(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(path, legacy_rows())

    store = MetricsStore(path)

    assert store.schema_version() == SCHEMA_VERSION
    assert store.count_samples() == 2

    migrated = canonical_rows(path)
    assert len(migrated) == 2
    assert migrated[0]["legacy_sample_id"] == 1
    assert migrated[0]["legacy_recorded_at"] == "2026-11-09T12:00:00+00:00"
    assert migrated[0]["observed_at"] == "2026-11-09T12:00:00+00:00"
    assert migrated[0]["source"] == "windows_host"
    assert migrated[0]["scope"] == "aggregate_gateway"
    assert migrated[0]["download_mbps"] == 12.5
    assert migrated[0]["upload_mbps"] == 2.5
    assert migrated[0]["rtt_ms"] == 15.0
    assert migrated[0]["rtt_variation_ms"] == 2.5
    assert migrated[0]["packet_loss_percent"] == 10.0
    assert migrated[0]["quality"] == "unknown"
    assert migrated[0]["client_id"] is None

    assert migrated[1]["source"] == "windows_hotspot"
    assert migrated[1]["scope"] == "aggregate_hotspot"
    assert migrated[1]["download_mbps"] == 4.0
    assert migrated[1]["upload_mbps"] == 1.0


def test_unknown_legacy_label_keeps_unknown_provenance(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(
        path,
        (
            (
                "2026-11-09T12:00:00+00:00",
                "Mystery Adapter",
                1.0,
                0.5,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        ),
    )

    MetricsStore(path)

    row = canonical_rows(path)[0]
    assert row["source"] == "unknown"
    assert row["scope"] == "aggregate_gateway"
    assert row["legacy_recorded_at"] == "2026-11-09T12:00:00+00:00"


def test_naive_legacy_timestamp_is_normalized_without_losing_original(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(
        path,
        (
            (
                "2026-11-09T12:00:00",
                "Wi-Fi",
                1.0,
                0.5,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        ),
    )

    MetricsStore(path)

    row = canonical_rows(path)[0]
    assert row["observed_at"] == "2026-11-09T12:00:00+00:00"
    assert row["legacy_recorded_at"] == "2026-11-09T12:00:00"


def test_malformed_legacy_timestamp_is_preserved_but_not_invented(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(
        path,
        (
            (
                "not-a-timestamp",
                "Wi-Fi",
                1.0,
                0.5,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        ),
    )

    store = MetricsStore(path)

    assert store.count_samples() == 1
    assert canonical_rows(path) == []


def test_repeated_initialization_does_not_duplicate_migrated_rows(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(path, legacy_rows())

    MetricsStore(path)
    first = canonical_rows(path)
    MetricsStore(path)
    second = canonical_rows(path)

    assert len(first) == 2
    assert len(second) == 2
    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert [row["legacy_sample_id"] for row in second] == [1, 2]


def test_replaying_migration_from_zero_does_not_duplicate_rows(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(path, legacy_rows())
    MetricsStore(path)

    connection = sqlite3.connect(path)

    try:
        connection.execute("PRAGMA user_version = 0")
        connection.commit()

    finally:
        connection.close()

    MetricsStore(path)

    assert len(canonical_rows(path)) == 2


def test_failed_migration_rolls_back_and_keeps_legacy_data(tmp_path):
    path = tmp_path / "broken.sqlite3"
    connection = sqlite3.connect(path)

    try:
        connection.execute(
            """
            CREATE TABLE network_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                interface_label TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO network_samples (recorded_at, interface_label) VALUES (?, ?)",
            ("2026-11-09T12:00:00+00:00", "Wi-Fi"),
        )
        connection.commit()

    finally:
        connection.close()

    with pytest.raises(MigrationError):
        MetricsStore(path)

    connection = sqlite3.connect(path)

    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        rows = connection.execute(
            "SELECT recorded_at, interface_label FROM network_samples"
        ).fetchall()

    finally:
        connection.close()

    assert version == 0
    assert "network_samples" in tables
    assert "telemetry_observations" not in tables
    assert rows == [("2026-11-09T12:00:00+00:00", "Wi-Fi")]


def test_corrupt_database_is_detected_without_overwriting_it(tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    original = b"this is not a sqlite database"
    path.write_bytes(original)

    with pytest.raises(CorruptDatabaseError):
        MetricsStore(path)

    assert path.read_bytes() == original


def test_legacy_table_and_index_remain_after_migration(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(path, legacy_rows())

    MetricsStore(path)

    connection = sqlite3.connect(path)

    try:
        objects = {
            (row[0], row[1])
            for row in connection.execute(
                "SELECT type, name FROM sqlite_master"
            )
        }
        legacy_count = connection.execute(
            "SELECT COUNT(*) FROM network_samples"
        ).fetchone()[0]

    finally:
        connection.close()

    assert ("table", "network_samples") in objects
    assert ("index", "idx_network_samples_recorded_at") in objects
    assert legacy_count == 2

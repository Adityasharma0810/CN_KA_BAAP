
"""
Experience Budget - V0.5
Privacy-preserving historical metrics storage.

Stores aggregate network measurements only.
Does not store connected-device identities or private traffic data.
"""

import ipaddress
import math
import sqlite3

from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB_PATH = "data/experience_budget.sqlite3"
SCHEMA_VERSION = 1
OBSERVATIONS_TABLE = "telemetry_observations"
CLIENTS_TABLE = "anonymous_clients"


class StorageError(RuntimeError):
    """Base class for safe, non-sensitive storage failures."""


class MigrationError(StorageError):
    """Raised when a schema migration cannot be completed safely."""


class CorruptDatabaseError(StorageError):
    """Raised when SQLite reports that the database is not readable."""

ALLOWED_FIELDS = {
    "recorded_at",
    "interface_label",
    "download_mbps",
    "upload_mbps",
    "adapter_up",
    "internet_reachable",
    "probe_target",
    "probes_sent",
    "probes_received",
    "packet_loss_percent",
    "rtt_min_ms",
    "rtt_avg_ms",
    "rtt_max_ms",
    "rtt_jitter_avg_ms",
}

NUMERIC_FIELDS = {
    "download_mbps",
    "upload_mbps",
    "packet_loss_percent",
    "rtt_min_ms",
    "rtt_avg_ms",
    "rtt_max_ms",
    "rtt_jitter_avg_ms",
}

INTEGER_FIELDS = {
    "probes_sent",
    "probes_received",
}

BOOLEAN_FIELDS = {
    "adapter_up",
    "internet_reachable",
}

COLUMNS = (
    "recorded_at",
    "interface_label",
    "download_mbps",
    "upload_mbps",
    "adapter_up",
    "internet_reachable",
    "probe_target",
    "probes_sent",
    "probes_received",
    "packet_loss_percent",
    "rtt_min_ms",
    "rtt_avg_ms",
    "rtt_max_ms",
    "rtt_jitter_avg_ms",
)

_MIGRATION_1_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS anonymous_clients (
        client_id TEXT PRIMARY KEY
            CHECK (
                length(client_id) BETWEEN 14 AND 40
                AND client_id GLOB 'client-[a-z0-9]*'
            ),
        display_label TEXT NOT NULL UNIQUE
            CHECK (display_label GLOB 'Client [0-9][0-9]*'),
        environment TEXT NOT NULL
            CHECK (environment IN ('physical_host', 'simulated_lab')),
        simulated_lab_slot INTEGER
            CHECK (simulated_lab_slot IS NULL OR simulated_lab_slot > 0),
        first_seen_at TEXT,
        last_seen_at TEXT,
        created_at TEXT NOT NULL,
        CHECK (
            simulated_lab_slot IS NULL
            OR environment = 'simulated_lab'
        ),
        UNIQUE (environment, simulated_lab_slot)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS telemetry_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observed_at TEXT NOT NULL,
        source TEXT NOT NULL
            CHECK (source IN (
                'windows_host', 'windows_hotspot', 'linux_gateway',
                'linux_namespace_lab', 'unknown'
            )),
        scope TEXT NOT NULL
            CHECK (scope IN (
                'aggregate_gateway', 'aggregate_hotspot', 'client'
            )),
        environment TEXT NOT NULL
            CHECK (environment IN ('physical_host', 'simulated_lab')),
        quality TEXT NOT NULL
            CHECK (quality IN ('measured', 'derived', 'unavailable', 'unknown')),
        stale INTEGER NOT NULL DEFAULT 0
            CHECK (stale IN (0, 1)),
        collector_error TEXT
            CHECK (collector_error IS NULL OR length(collector_error) <= 200),
        client_id TEXT
            REFERENCES anonymous_clients(client_id) ON DELETE RESTRICT,
        download_bytes INTEGER
            CHECK (download_bytes IS NULL OR download_bytes >= 0),
        upload_bytes INTEGER
            CHECK (upload_bytes IS NULL OR upload_bytes >= 0),
        download_packets INTEGER
            CHECK (download_packets IS NULL OR download_packets >= 0),
        upload_packets INTEGER
            CHECK (upload_packets IS NULL OR upload_packets >= 0),
        download_mbps REAL
            CHECK (download_mbps IS NULL OR download_mbps >= 0),
        upload_mbps REAL
            CHECK (upload_mbps IS NULL OR upload_mbps >= 0),
        rtt_ms REAL
            CHECK (rtt_ms IS NULL OR rtt_ms >= 0),
        packet_loss_percent REAL
            CHECK (
                packet_loss_percent IS NULL
                OR (packet_loss_percent >= 0 AND packet_loss_percent <= 100)
            ),
        rtt_variation_ms REAL
            CHECK (rtt_variation_ms IS NULL OR rtt_variation_ms >= 0),
        queue_depth_bytes INTEGER
            CHECK (queue_depth_bytes IS NULL OR queue_depth_bytes >= 0),
        queue_delay_ms REAL
            CHECK (queue_delay_ms IS NULL OR queue_delay_ms >= 0),
        legacy_sample_id INTEGER UNIQUE,
        legacy_recorded_at TEXT,
        CHECK (
            (scope = 'client' AND client_id IS NOT NULL)
            OR (scope <> 'client' AND client_id IS NULL)
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_observations_observed_at
    ON telemetry_observations(observed_at, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_observations_scope_observed_at
    ON telemetry_observations(scope, observed_at, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_observations_client_observed_at
    ON telemetry_observations(client_id, observed_at, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_observations_source_observed_at
    ON telemetry_observations(source, observed_at, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_observations_environment_observed_at
    ON telemetry_observations(environment, observed_at, id)
    """,
)

_LEGACY_SELECT = """
    SELECT
        id,
        recorded_at,
        interface_label,
        download_mbps,
        upload_mbps,
        packet_loss_percent,
        rtt_avg_ms,
        rtt_jitter_avg_ms
    FROM network_samples
    ORDER BY id
"""

_LEGACY_INSERT = """
    INSERT INTO telemetry_observations (
        observed_at,
        source,
        scope,
        environment,
        quality,
        stale,
        collector_error,
        client_id,
        download_bytes,
        upload_bytes,
        download_packets,
        upload_packets,
        download_mbps,
        upload_mbps,
        rtt_ms,
        packet_loss_percent,
        rtt_variation_ms,
        queue_depth_bytes,
        queue_delay_ms,
        legacy_sample_id,
        legacy_recorded_at
    )
    SELECT
        ?, ?, ?, ?, 'unknown', 0, NULL, NULL,
        NULL, NULL, NULL, NULL,
        ?, ?, ?, ?, ?,
        NULL, NULL, ?, ?
    WHERE NOT EXISTS (
        SELECT 1
        FROM telemetry_observations
        WHERE legacy_sample_id = ?
    )
"""


def _parse_legacy_timestamp(value):
    """Return an aware UTC datetime, or raise ValueError for unsafe text."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("legacy timestamp is empty")

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("legacy timestamp is not ISO 8601") from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _legacy_source_and_scope(interface_label):
    """Map the only legacy labels we can establish without inventing provenance."""

    if interface_label == "hotspot-aggregate":
        return "windows_hotspot", "aggregate_hotspot"
    if interface_label == "Wi-Fi":
        return "windows_host", "aggregate_gateway"
    return "unknown", "aggregate_gateway"


def _is_corrupt_database_error(error):
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "file is not a database",
            "database disk image is malformed",
            "malformed database",
        )
    )


class MetricsStore:
    """SQLite storage for aggregate network metrics."""

    def get_samples_by_interface(self, interface_label, limit=100):
        """Retrieve measurements for one interface only."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("Limit must be a positive integer.")

        connection = self._connect()

        try:
            rows = connection.execute(
                """
                SELECT * FROM network_samples
                WHERE interface_label = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (interface_label, limit),
            ).fetchall()

            return [dict(row) for row in rows]

        finally:
            connection.close()



    
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self):
        """Create the legacy table, then apply pending schema migrations."""

        connection = self._connect()

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS network_samples (
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
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_network_samples_recorded_at
                ON network_samples(recorded_at)
                """
            )

            connection.commit()

        except sqlite3.DatabaseError as error:
            connection.rollback()
            if _is_corrupt_database_error(error):
                raise CorruptDatabaseError(
                    "database is corrupt or unreadable"
                ) from error
            raise StorageError("database initialization failed") from error

        finally:
            connection.close()

        self.apply_migrations()

    def schema_version(self):
        """Return the current PRAGMA user_version value."""

        connection = self._connect()

        try:
            row = connection.execute("PRAGMA user_version").fetchone()
            return int(row[0])

        finally:
            connection.close()

    def apply_migrations(self):
        """Apply pending migrations in one transaction, or roll back fully."""

        connection = self._connect()

        try:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])

            if current > SCHEMA_VERSION:
                raise MigrationError(
                    "database schema is newer than this application"
                )

            if current == SCHEMA_VERSION:
                return current

            connection.execute("BEGIN IMMEDIATE")

            try:
                if current < 1:
                    self._apply_migration_1(connection)

                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.commit()

            except Exception as error:
                connection.rollback()
                raise MigrationError("database migration failed") from error

            return SCHEMA_VERSION

        except sqlite3.DatabaseError as error:
            connection.rollback()
            if _is_corrupt_database_error(error):
                raise CorruptDatabaseError(
                    "database is corrupt or unreadable"
                ) from error
            raise StorageError("database migration could not run") from error

        finally:
            connection.close()

    @staticmethod
    def _apply_migration_1(connection):
        """Add canonical tables and copy compatible legacy rows."""

        for statement in _MIGRATION_1_STATEMENTS:
            connection.execute(statement)

        for row in connection.execute(_LEGACY_SELECT).fetchall():
            try:
                observed_at = _parse_legacy_timestamp(row["recorded_at"])
            except ValueError:
                # The original row remains untouched in network_samples.
                continue

            source, scope = _legacy_source_and_scope(row["interface_label"])

            connection.execute(
                _LEGACY_INSERT,
                (
                    observed_at.isoformat(),
                    source,
                    scope,
                    "physical_host",
                    row["download_mbps"],
                    row["upload_mbps"],
                    row["rtt_avg_ms"],
                    row["packet_loss_percent"],
                    row["rtt_jitter_avg_ms"],
                    row["id"],
                    row["recorded_at"],
                    row["id"],
                ),
            )

    def _validate(self, sample):
        if not isinstance(sample, dict):
            raise ValueError("Sample must be a dictionary.")

        unknown = set(sample) - ALLOWED_FIELDS

        if unknown:
            raise ValueError(
                f"Unsupported fields: {sorted(unknown)}"
            )

        row = {
            field: sample.get(field)
            for field in COLUMNS
        }

        if row["recorded_at"] is None:
            row["recorded_at"] = datetime.now(
                timezone.utc
            ).isoformat()

        if (
            not isinstance(row["recorded_at"], str)
            or not row["recorded_at"].strip()
        ):
            raise ValueError("Invalid timestamp.")

        if row["interface_label"] is None:
            row["interface_label"] = "Wi-Fi"

        if (
            not isinstance(row["interface_label"], str)
            or not row["interface_label"].strip()
        ):
            raise ValueError("Invalid interface label.")

        for field in NUMERIC_FIELDS:
            value = row[field]

            if value is None:
                continue

            if isinstance(value, bool):
                raise ValueError(f"Invalid numeric field: {field}")

            if not isinstance(value, (int, float)):
                raise ValueError(f"Invalid numeric field: {field}")

            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid value for {field}")

        for field in INTEGER_FIELDS:
            value = row[field]

            if value is not None:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                ):
                    raise ValueError(f"Invalid value for {field}")

        for field in BOOLEAN_FIELDS:
            value = row[field]

            if value is not None and not isinstance(value, bool):
                raise ValueError(f"Invalid boolean field: {field}")

        if (
            row["packet_loss_percent"] is not None
            and row["packet_loss_percent"] > 100
        ):
            raise ValueError("Packet loss cannot exceed 100%.")

        sent = row["probes_sent"]
        received = row["probes_received"]

        if sent is not None and received is not None:
            if received > sent:
                raise ValueError(
                    "Received probes cannot exceed sent probes."
                )

        target = row["probe_target"]

        if target is not None:
            if not isinstance(target, str):
                raise ValueError("Invalid public probe target.")

            try:
                ipaddress.ip_address(target)
            except ValueError as error:
                raise ValueError(
                    "Probe target must be a numeric IP address."
                ) from error

        for field in BOOLEAN_FIELDS:
            if row[field] is not None:
                row[field] = int(row[field])

        return row

    def insert_sample(self, sample):
        """Validate and insert one aggregate measurement."""

        row = self._validate(sample)

        placeholders = ", ".join("?" for _ in COLUMNS)
        columns = ", ".join(COLUMNS)

        values = tuple(row[column] for column in COLUMNS)

        connection = self._connect()

        try:
            cursor = connection.execute(
                f"""
                INSERT INTO network_samples ({columns})
                VALUES ({placeholders})
                """,
                values,
            )

            connection.commit()

            return cursor.lastrowid

        finally:
            connection.close()

    def get_recent_samples(self, limit=100):
        """Return the newest measurements first."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
        ):
            raise ValueError("Limit must be a positive integer.")

        connection = self._connect()

        try:
            rows = connection.execute(
                """
                SELECT * FROM network_samples
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

        finally:
            connection.close()

    def count_samples(self):
        """Return total number of stored measurements."""

        connection = self._connect()

        try:
            result = connection.execute(
                "SELECT COUNT(*) FROM network_samples"
            ).fetchone()

            return result[0]

        finally:
            connection.close()

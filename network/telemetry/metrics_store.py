
"""
Experience Budget - V0.5
Privacy-preserving historical metrics storage.

Stores aggregate network measurements only.
Does not store connected-device identities or private traffic data.
"""

import ipaddress
import math
import re
import sqlite3

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from backend.app.models.schemas import (
    ClientId,
    ObservationEnvironment,
    ObservationMetadata,
    ObservationScope,
    TelemetryObservation,
)


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


_DISPLAY_LABEL_PATTERN = re.compile(r"^Client [0-9]{2,}$")
_MAX_SIMULATED_LAB_SLOT = 99
_MAX_OBSERVATION_BATCH = 500
_CLIENT_ID_ADAPTER = TypeAdapter(ClientId)
_SAFE_ERROR_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,99}$")
_FORBIDDEN_ERROR_TERMS = (
    "ip",
    "mac",
    "device",
    "hostname",
    "address",
    "password",
    "secret",
    "token",
    "credential",
    "client-",
    "veth",
    "wlan",
    "eth",
    "enp",
    "br-",
    "sys",
    "etc",
    "users",
    "/",
    "\\",
)


class StoredAnonymousClient(BaseModel):
    """Persisted anonymous client record with no identity or address fields."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    client_id: ClientId
    display_label: str = Field(pattern=r"^Client [0-9]{2,}$")
    environment: ObservationEnvironment
    simulated_lab_slot: int | None = Field(default=None, ge=1)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    @field_validator("first_seen_at", "last_seen_at")
    @classmethod
    def require_utc_if_present(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("client timestamps must include a timezone")
        return value.astimezone(timezone.utc)


class StoredObservation(BaseModel):
    """A persisted shared observation plus its storage identifiers."""

    model_config = ConfigDict(extra="forbid")

    id: int
    legacy_sample_id: int | None = None
    observation: TelemetryObservation


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


_OBSERVATION_INSERT = """
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
        queue_delay_ms
    )
    VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?, ?, ?
    )
"""


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _safe_collector_error(value):
    """Allow only short, controlled error codes; reject identity-like text."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("collector_error must be a string or None")

    value = value.strip()
    if not value or _SAFE_ERROR_PATTERN.fullmatch(value) is None:
        raise ValueError("collector_error must be a short safe code")

    lowered = value.lower()
    if any(term in lowered for term in _FORBIDDEN_ERROR_TERMS):
        raise ValueError("collector_error contains forbidden identity data")

    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError("collector_error must not contain an address")


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

    @staticmethod
    def _coerce_client_id(client_id):
        try:
            return _CLIENT_ID_ADAPTER.validate_python(client_id)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid anonymous client ID") from error

    @staticmethod
    def _coerce_utc(value, field_name):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValueError(f"{field_name} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must include a timezone")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _client_from_row(row):
        return StoredAnonymousClient(
            client_id=row["client_id"],
            display_label=row["display_label"],
            environment=row["environment"],
            simulated_lab_slot=row["simulated_lab_slot"],
            first_seen_at=(
                datetime.fromisoformat(row["first_seen_at"])
                if row["first_seen_at"]
                else None
            ),
            last_seen_at=(
                datetime.fromisoformat(row["last_seen_at"])
                if row["last_seen_at"]
                else None
            ),
        )

    def register_client(
        self,
        client_id,
        display_label,
        *,
        environment=ObservationEnvironment.PHYSICAL_HOST,
        simulated_lab_slot=None,
        first_seen_at=None,
        last_seen_at=None,
    ):
        """Register or idempotently update one anonymous client record."""

        client_id = self._coerce_client_id(client_id)

        if (
            not isinstance(display_label, str)
            or _DISPLAY_LABEL_PATTERN.fullmatch(display_label) is None
        ):
            raise ValueError("display_label must look like 'Client 01'")

        try:
            environment = ObservationEnvironment(environment)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid observation environment") from error

        if simulated_lab_slot is not None:
            if (
                isinstance(simulated_lab_slot, bool)
                or not isinstance(simulated_lab_slot, int)
                or simulated_lab_slot < 1
                or simulated_lab_slot > _MAX_SIMULATED_LAB_SLOT
            ):
                raise ValueError("simulated_lab_slot must be a positive integer")
            if environment != ObservationEnvironment.SIMULATED_LAB:
                raise ValueError(
                    "simulated_lab_slot requires the simulated_lab environment"
                )

        first_seen_at = self._coerce_utc(first_seen_at, "first_seen_at")
        last_seen_at = self._coerce_utc(last_seen_at, "last_seen_at")

        if (
            first_seen_at is not None
            and last_seen_at is not None
            and first_seen_at > last_seen_at
        ):
            raise ValueError("first_seen_at must not follow last_seen_at")

        if first_seen_at is None and last_seen_at is not None:
            first_seen_at = last_seen_at

        connection = self._connect()

        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM anonymous_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()

            if existing is not None:
                if (
                    existing["display_label"] != display_label
                    or existing["environment"] != environment.value
                    or existing["simulated_lab_slot"] != simulated_lab_slot
                ):
                    raise ValueError("conflicting anonymous client record")

                merged_first = self._earlier(
                    existing["first_seen_at"], first_seen_at
                )
                merged_last = self._later(existing["last_seen_at"], last_seen_at)
                connection.execute(
                    """
                    UPDATE anonymous_clients
                    SET first_seen_at = ?, last_seen_at = ?
                    WHERE client_id = ?
                    """,
                    (merged_first, merged_last, client_id),
                )
                connection.commit()
                return self._client_from_row(
                    connection.execute(
                        "SELECT * FROM anonymous_clients WHERE client_id = ?",
                        (client_id,),
                    ).fetchone()
                )

            label_owner = connection.execute(
                "SELECT client_id FROM anonymous_clients WHERE display_label = ?",
                (display_label,),
            ).fetchone()
            if label_owner is not None:
                raise ValueError("display label is already assigned")

            if simulated_lab_slot is not None:
                slot_owner = connection.execute(
                    """
                    SELECT client_id FROM anonymous_clients
                    WHERE environment = ? AND simulated_lab_slot = ?
                    """,
                    (environment.value, simulated_lab_slot),
                ).fetchone()
                if slot_owner is not None:
                    raise ValueError("simulated lab slot is already assigned")

            connection.execute(
                """
                INSERT INTO anonymous_clients (
                    client_id,
                    display_label,
                    environment,
                    simulated_lab_slot,
                    first_seen_at,
                    last_seen_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    display_label,
                    environment.value,
                    simulated_lab_slot,
                    first_seen_at.isoformat() if first_seen_at else None,
                    last_seen_at.isoformat() if last_seen_at else None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

            return self._client_from_row(
                connection.execute(
                    "SELECT * FROM anonymous_clients WHERE client_id = ?",
                    (client_id,),
                ).fetchone()
            )

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def get_client(self, client_id):
        """Return one persisted anonymous client by opaque ID."""

        client_id = self._coerce_client_id(client_id)
        connection = self._connect()

        try:
            row = connection.execute(
                "SELECT * FROM anonymous_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()

            if row is None:
                raise KeyError("unknown anonymous client")

            return self._client_from_row(row)

        finally:
            connection.close()

    def list_clients(self):
        """Return persisted clients in numeric display-label order."""

        connection = self._connect()

        try:
            rows = connection.execute(
                "SELECT * FROM anonymous_clients"
            ).fetchall()
            clients = [self._client_from_row(row) for row in rows]
            return sorted(
                clients,
                key=lambda client: int(client.display_label.split()[1]),
            )

        finally:
            connection.close()

    def get_simulated_client_by_slot(self, simulated_lab_slot):
        """Return the configured simulated-lab client for one slot, if any."""

        if (
            isinstance(simulated_lab_slot, bool)
            or not isinstance(simulated_lab_slot, int)
            or simulated_lab_slot < 1
            or simulated_lab_slot > _MAX_SIMULATED_LAB_SLOT
        ):
            raise ValueError("simulated_lab_slot must be a positive integer")

        connection = self._connect()

        try:
            row = connection.execute(
                """
                SELECT * FROM anonymous_clients
                WHERE environment = 'simulated_lab'
                  AND simulated_lab_slot = ?
                """,
                (simulated_lab_slot,),
            ).fetchone()

            return self._client_from_row(row) if row is not None else None

        finally:
            connection.close()

    @staticmethod
    def _earlier(current, candidate):
        if current is None:
            return candidate.isoformat() if candidate else None
        current_time = datetime.fromisoformat(current)
        if candidate is None or current_time <= candidate:
            return current
        return candidate.isoformat()

    @staticmethod
    def _later(current, candidate):
        if current is None:
            return candidate.isoformat() if candidate else None
        current_time = datetime.fromisoformat(current)
        if candidate is None or current_time >= candidate:
            return current
        return candidate.isoformat()

    @staticmethod
    def _observation_from_row(row):
        observed_at = datetime.fromisoformat(row["observed_at"])
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)

        metadata = ObservationMetadata(
            observed_at=observed_at,
            source=row["source"],
            scope=row["scope"],
            quality=row["quality"],
            environment=row["environment"],
            stale=bool(row["stale"]),
            collector_error=row["collector_error"],
            client_id=row["client_id"],
        )
        observation = TelemetryObservation(
            metadata=metadata,
            download_bytes=row["download_bytes"],
            upload_bytes=row["upload_bytes"],
            download_packets=row["download_packets"],
            upload_packets=row["upload_packets"],
            download_mbps=row["download_mbps"],
            upload_mbps=row["upload_mbps"],
            rtt_ms=row["rtt_ms"],
            packet_loss_percent=row["packet_loss_percent"],
            rtt_variation_ms=row["rtt_variation_ms"],
            queue_depth_bytes=row["queue_depth_bytes"],
            queue_delay_ms=row["queue_delay_ms"],
        )
        return StoredObservation(
            id=row["id"],
            legacy_sample_id=row["legacy_sample_id"],
            observation=observation,
        )

    def _observation_values(self, observation):
        if isinstance(observation, dict):
            observation = TelemetryObservation.model_validate(observation)
        elif not isinstance(observation, TelemetryObservation):
            raise TypeError("observation must be a TelemetryObservation or mapping")

        for field in (
            "download_mbps",
            "upload_mbps",
            "rtt_ms",
            "packet_loss_percent",
            "rtt_variation_ms",
            "queue_delay_ms",
        ):
            value = getattr(observation, field)
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise ValueError(f"invalid numeric field: {field}")

        metadata = observation.metadata
        source = _enum_value(metadata.source)
        scope = _enum_value(metadata.scope)
        environment = _enum_value(metadata.environment)
        quality = _enum_value(metadata.quality)

        if scope == ObservationScope.CLIENT.value and metadata.client_id is None:
            raise ValueError("client observations require an anonymous client_id")
        if scope != ObservationScope.CLIENT.value and metadata.client_id is not None:
            raise ValueError("aggregate observations cannot contain client_id")

        return (
            metadata.observed_at.astimezone(timezone.utc).isoformat(),
            source,
            scope,
            environment,
            quality,
            1 if metadata.stale else 0,
            _safe_collector_error(metadata.collector_error),
            metadata.client_id,
            observation.download_bytes,
            observation.upload_bytes,
            observation.download_packets,
            observation.upload_packets,
            observation.download_mbps,
            observation.upload_mbps,
            observation.rtt_ms,
            observation.packet_loss_percent,
            observation.rtt_variation_ms,
            observation.queue_depth_bytes,
            observation.queue_delay_ms,
        )

    @staticmethod
    def _require_clients(connection, client_ids):
        if not client_ids:
            return

        placeholders = ", ".join("?" for _ in client_ids)
        rows = connection.execute(
            f"""
            SELECT client_id FROM anonymous_clients
            WHERE client_id IN ({placeholders})
            """,
            tuple(client_ids),
        ).fetchall()
        found = {row["client_id"] for row in rows}
        if found != set(client_ids):
            raise ValueError(
                "client observation requires a registered anonymous client"
            )

    def _touch_clients(self, connection, values):
        observed = {}

        for row in values:
            client_id = row[7]
            if client_id is None:
                continue
            observed_at = datetime.fromisoformat(row[0])
            if client_id not in observed:
                observed[client_id] = [observed_at, observed_at]
            else:
                observed[client_id][0] = min(
                    observed[client_id][0], observed_at
                )
                observed[client_id][1] = max(
                    observed[client_id][1], observed_at
                )

        for client_id, (first_seen, last_seen) in observed.items():
            existing = connection.execute(
                """
                SELECT first_seen_at, last_seen_at
                FROM anonymous_clients
                WHERE client_id = ?
                """,
                (client_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE anonymous_clients
                SET first_seen_at = ?, last_seen_at = ?
                WHERE client_id = ?
                """,
                (
                    self._earlier(existing["first_seen_at"], first_seen),
                    self._later(existing["last_seen_at"], last_seen),
                    client_id,
                ),
            )

    def save_observations(self, observations):
        """Validate and insert a bounded batch atomically."""

        if isinstance(observations, (str, bytes, dict)):
            raise TypeError("observations must be an iterable of observations")

        try:
            items = list(observations)
        except TypeError as error:
            raise TypeError("observations must be an iterable") from error

        if len(items) > _MAX_OBSERVATION_BATCH:
            raise ValueError("observation batch is too large")
        if not items:
            return []

        values = [self._observation_values(item) for item in items]
        client_ids = {row[7] for row in values if row[7] is not None}

        connection = self._connect()

        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_clients(connection, client_ids)

            ids = []
            for row in values:
                cursor = connection.execute(_OBSERVATION_INSERT, row)
                ids.append(cursor.lastrowid)

            self._touch_clients(connection, values)
            connection.commit()
            return ids

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def save_observation(self, observation):
        """Validate and insert one shared observation."""

        return self.save_observations([observation])[0]

    def get_observation(self, observation_id):
        """Return one stored observation, or ``None`` when absent."""

        if (
            isinstance(observation_id, bool)
            or not isinstance(observation_id, int)
            or observation_id < 1
        ):
            raise ValueError("observation_id must be a positive integer")

        connection = self._connect()

        try:
            row = connection.execute(
                """
                SELECT * FROM telemetry_observations
                WHERE id = ?
                """,
                (observation_id,),
            ).fetchone()

            return self._observation_from_row(row) if row is not None else None

        finally:
            connection.close()

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

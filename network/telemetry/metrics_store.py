
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


class MetricsStore:
    """SQLite storage for aggregate network metrics."""

    def get_samples_by_interface(self, interface_label, limit=100):
        """Retrieve measurements for one interface only."""

        return self.query_history(interface_label=interface_label, limit=limit)

    def query_history(
        self,
        *,
        interface_label=None,
        start=None,
        end=None,
        limit=100,
        offset=0,
        order="desc",
    ):
        """Return bounded aggregate history using validated SQL parameters."""

        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ValueError("Limit must be between 1 and 1000.")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Offset must be a non-negative integer.")
        if order not in {"asc", "desc"}:
            raise ValueError("Order must be asc or desc.")
        if start is not None and end is not None and start > end:
            raise ValueError("Start must not be after end.")

        clauses = []
        parameters = []
        if interface_label is not None:
            clauses.append("interface_label = ?")
            parameters.append(interface_label)
        if start is not None:
            clauses.append("recorded_at >= ?")
            parameters.append(start)
        if end is not None:
            clauses.append("recorded_at <= ?")
            parameters.append(end)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        direction = "ASC" if order == "asc" else "DESC"

        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT * FROM network_samples
                {where}
                ORDER BY recorded_at {direction}, id {direction}
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
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
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        """Create the aggregate measurements table."""

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

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from network.telemetry.metrics_store import MetricsStore, StoredObservation


T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    return MetricsStore(tmp_path / "observations.sqlite3")


def metadata(**overrides):
    values = {
        "observed_at": T0,
        "source": ObservationSource.WINDOWS_HOST,
        "scope": ObservationScope.AGGREGATE_GATEWAY,
        "quality": ValueQuality.MEASURED,
        "environment": ObservationEnvironment.PHYSICAL_HOST,
    }
    values.update(overrides)
    return values


def aggregate_observation(**overrides):
    values = {
        "metadata": metadata(),
        "download_bytes": 1000,
        "upload_bytes": 500,
        "download_packets": 10,
        "upload_packets": 5,
        "download_mbps": 12.5,
        "upload_mbps": 2.5,
        "rtt_ms": 15.0,
        "packet_loss_percent": 1.0,
        "rtt_variation_ms": 0.5,
        "queue_depth_bytes": 2048,
        "queue_delay_ms": 1.25,
    }
    values.update(overrides)
    return TelemetryObservation(**values)


def client_observation(client_id, **overrides):
    values = {
        "metadata": metadata(
            source=ObservationSource.LINUX_NAMESPACE_LAB,
            scope=ObservationScope.CLIENT,
            environment=ObservationEnvironment.SIMULATED_LAB,
            client_id=client_id,
        ),
        "download_bytes": 0,
        "upload_bytes": 0,
        "download_mbps": 0.0,
        "upload_mbps": 0.0,
    }
    values.update(overrides)
    return TelemetryObservation(**values)


def test_save_and_retrieve_aggregate_observation(store):
    observation_id = store.save_observation(aggregate_observation())

    stored = store.get_observation(observation_id)

    assert isinstance(stored, StoredObservation)
    assert stored.id == observation_id
    assert stored.legacy_sample_id is None
    assert stored.observation.download_bytes == 1000
    assert stored.observation.upload_bytes == 500
    assert stored.observation.download_packets == 10
    assert stored.observation.upload_packets == 5
    assert stored.observation.download_mbps == 12.5
    assert stored.observation.upload_mbps == 2.5
    assert stored.observation.rtt_ms == 15.0
    assert stored.observation.packet_loss_percent == 1.0
    assert stored.observation.rtt_variation_ms == 0.5
    assert stored.observation.queue_depth_bytes == 2048
    assert stored.observation.queue_delay_ms == 1.25
    assert stored.observation.metadata.source == "windows_host"
    assert stored.observation.metadata.scope == "aggregate_gateway"
    assert stored.observation.metadata.environment == "physical_host"
    assert stored.observation.metadata.quality == "measured"
    assert stored.observation.metadata.observed_at == T0


def test_missing_values_remain_none_and_zero_remains_zero(store):
    observation_id = store.save_observation(
        aggregate_observation(
            download_mbps=None,
            upload_mbps=0.0,
            rtt_ms=None,
            packet_loss_percent=None,
            rtt_variation_ms=None,
            queue_depth_bytes=None,
            queue_delay_ms=None,
        )
    )

    stored = store.get_observation(observation_id).observation

    assert stored.download_mbps is None
    assert stored.upload_mbps == 0.0
    assert stored.rtt_ms is None
    assert stored.packet_loss_percent is None
    assert stored.rtt_variation_ms is None
    assert stored.queue_depth_bytes is None
    assert stored.queue_delay_ms is None


def test_quality_staleness_and_provenance_are_preserved(store):
    observation_id = store.save_observation(
        aggregate_observation(
            metadata=metadata(
                source=ObservationSource.WINDOWS_HOTSPOT,
                scope=ObservationScope.AGGREGATE_HOTSPOT,
                quality=ValueQuality.DERIVED,
                stale=True,
                collector_error="rate_unavailable:no_baseline",
            )
        )
    )

    stored = store.get_observation(observation_id).observation

    assert stored.metadata.source == "windows_hotspot"
    assert stored.metadata.scope == "aggregate_hotspot"
    assert stored.metadata.quality == "derived"
    assert stored.metadata.stale is True
    assert stored.metadata.collector_error == "rate_unavailable:no_baseline"


def test_client_observation_requires_registered_client(store):
    with pytest.raises(ValueError, match="registered anonymous client"):
        store.save_observation(
            client_observation("client-0123456789abcdef")
        )

    assert store.get_observation(1) is None


def test_client_observation_updates_registered_client_seen_times(store):
    store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )

    store.save_observation(client_observation("client-0123456789abcdef"))

    client = store.get_client("client-0123456789abcdef")
    assert client.first_seen_at == T0
    assert client.last_seen_at == T0


def test_batch_save_is_atomic_and_updates_client_times(store):
    store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )

    ids = store.save_observations(
        [
            client_observation("client-0123456789abcdef"),
            client_observation(
                "client-0123456789abcdef",
                metadata=metadata(
                    observed_at=T0.replace(second=5),
                    source=ObservationSource.LINUX_NAMESPACE_LAB,
                    scope=ObservationScope.CLIENT,
                    environment=ObservationEnvironment.SIMULATED_LAB,
                    client_id="client-0123456789abcdef",
                ),
            ),
        ]
    )

    assert len(ids) == 2
    assert ids == [1, 2]
    client = store.get_client("client-0123456789abcdef")
    assert client.first_seen_at == T0
    assert client.last_seen_at == T0.replace(second=5)


def test_batch_validation_failure_writes_nothing(store):
    store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )

    with pytest.raises(ValueError, match="invalid observation"):
        store.save_observations(
            [
                aggregate_observation(),
                {
                    "metadata": metadata(),
                    "ip_address": "192.0.2.10",
                },
            ]
        )

    assert store.get_observation(1) is None


def test_invalid_numeric_values_are_rejected(store):
    for field in ("download_mbps", "upload_mbps", "rtt_ms", "queue_delay_ms"):
        for value in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises((ValueError, ValidationError)):
                store.save_observation(
                    aggregate_observation(**{field: value})
                )


def test_unsafe_collector_error_is_rejected(store):
    for value in (
        "failed for 192.0.2.10",
        "veth-c1-br",
        "client-0123456789abcdef",
        "C:\\Users\\Alice",
        "password=secret",
    ):
        with pytest.raises(ValueError, match="collector_error"):
            store.save_observation(
                aggregate_observation(
                    metadata=metadata(collector_error=value)
                )
            )

    assert store.get_observation(1) is None


def test_failed_save_does_not_corrupt_previous_rows(store):
    first = store.save_observation(aggregate_observation())

    with pytest.raises(ValueError):
        store.save_observation(
            aggregate_observation(
                metadata=metadata(collector_error="veth-c1-br")
            )
        )

    assert store.get_observation(first) is not None


def test_unknown_provenance_is_explicitly_storable(store):
    observation_id = store.save_observation(
        aggregate_observation(
            metadata=metadata(
                source=ObservationSource.UNKNOWN,
                quality=ValueQuality.UNKNOWN,
            )
        )
    )

    stored = store.get_observation(observation_id).observation
    assert stored.metadata.source == "unknown"
    assert stored.metadata.quality == "unknown"


def test_get_observation_validates_identifier(store):
    for value in (0, -1, True, "1"):
        with pytest.raises(ValueError):
            store.get_observation(value)


def test_migrated_legacy_row_is_readable_through_shared_model(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)

    try:
        connection.executescript(
            """
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
            """
        )
        connection.execute(
            """
            INSERT INTO network_samples (
                recorded_at, interface_label, download_mbps, upload_mbps,
                packet_loss_percent, rtt_avg_ms, rtt_jitter_avg_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-11-09T12:00:00+00:00",
                "Wi-Fi",
                12.5,
                2.5,
                1.0,
                15.0,
                0.5,
            ),
        )
        connection.commit()

    finally:
        connection.close()

    store = MetricsStore(path)
    stored = store.get_observation(1)

    assert stored.legacy_sample_id == 1
    assert stored.observation.metadata.source == "windows_host"
    assert stored.observation.metadata.quality == "unknown"
    assert stored.observation.download_mbps == 12.5
    assert stored.observation.rtt_ms == 15.0

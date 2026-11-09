import re
import sqlite3
from datetime import datetime, timezone

import pytest

from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from backend.app.services.client_registry import AnonymousClientRegistry
from network.telemetry.metrics_store import MetricsStore


T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
CLIENT_ID = "client-0123456789abcdef"
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
FORBIDDEN_TEXT = (
    "veth",
    "wlan",
    "enp",
    "hostname",
    "device name",
    "password",
    "secret",
    "token",
    "http://",
    "https://",
    "/etc/",
    "/home/",
    "c:\\",
)


@pytest.fixture
def populated_store(tmp_path):
    store = MetricsStore(tmp_path / "privacy.sqlite3")
    store.register_client(
        CLIENT_ID,
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
        first_seen_at=T0,
        last_seen_at=T0,
    )
    store.save_observations(
        [
            TelemetryObservation(
                metadata={
                    "observed_at": T0,
                    "source": ObservationSource.WINDOWS_HOST,
                    "scope": ObservationScope.AGGREGATE_GATEWAY,
                    "quality": ValueQuality.MEASURED,
                    "environment": ObservationEnvironment.PHYSICAL_HOST,
                },
                download_mbps=12.5,
            ),
            TelemetryObservation(
                metadata={
                    "observed_at": T0,
                    "source": ObservationSource.LINUX_NAMESPACE_LAB,
                    "scope": ObservationScope.CLIENT,
                    "quality": ValueQuality.UNAVAILABLE,
                    "environment": ObservationEnvironment.SIMULATED_LAB,
                    "client_id": CLIENT_ID,
                    "collector_error": "rate_unavailable:no_baseline",
                },
                download_bytes=100,
            ),
        ]
    )
    return store


def table_columns(path, table):
    connection = sqlite3.connect(path)

    try:
        return {
            row[1]: row[2]
            for row in connection.execute(f"PRAGMA table_info({table})")
        }

    finally:
        connection.close()


def all_values(path):
    connection = sqlite3.connect(path)

    try:
        values = []
        for table in ("anonymous_clients", "telemetry_observations"):
            for row in connection.execute(f"SELECT * FROM {table}"):
                values.extend(str(value) for value in row if value is not None)
        return values

    finally:
        connection.close()


def assert_private_text_is_absent(values):
    text = "\n".join(values).lower()
    assert IPV4.search(text) is None
    assert MAC.search(text) is None
    for term in FORBIDDEN_TEXT:
        assert term not in text


def test_canonical_schema_has_no_identity_or_json_columns(populated_store):
    client_columns = table_columns(populated_store.db_path, "anonymous_clients")
    observation_columns = table_columns(
        populated_store.db_path, "telemetry_observations"
    )

    assert "client_id" in client_columns
    assert "display_label" in client_columns
    assert "simulated_lab_slot" in client_columns
    assert "client_id" in observation_columns
    assert "collector_error" in observation_columns

    for columns in (client_columns, observation_columns):
        for name, declared_type in columns.items():
            lowered = name.lower()
            assert not any(
                term in lowered
                for term in (
                    "ip",
                    "mac",
                    "hostname",
                    "device",
                    "address",
                    "url",
                    "payload",
                    "credential",
                )
            )
            assert "json" not in declared_type.lower()
            assert "blob" not in declared_type.lower()


def test_persisted_rows_contain_no_identity_or_address_data(populated_store):
    assert_private_text_is_absent(all_values(populated_store.db_path))


def test_public_serialized_objects_have_only_allowed_fields(populated_store):
    observation = populated_store.get_observation(1)
    client = populated_store.get_client(CLIENT_ID)

    observation_data = observation.model_dump(mode="json")
    client_data = client.model_dump(mode="json")

    assert set(observation_data) == {
        "id",
        "legacy_sample_id",
        "observation",
    }
    assert set(client_data) == {
        "client_id",
        "display_label",
        "environment",
        "simulated_lab_slot",
        "first_seen_at",
        "last_seen_at",
    }
    assert_private_text_is_absent([str(observation_data), str(client_data)])


def test_unsafe_error_input_is_not_echoed(populated_store):
    with pytest.raises(ValueError) as captured:
        populated_store.save_observation(
            TelemetryObservation(
                metadata={
                    "observed_at": T0,
                    "source": ObservationSource.WINDOWS_HOST,
                    "scope": ObservationScope.AGGREGATE_GATEWAY,
                    "quality": ValueQuality.MEASURED,
                    "environment": ObservationEnvironment.PHYSICAL_HOST,
                    "collector_error": "failed at 192.0.2.10",
                }
            )
        )

    message = str(captured.value)
    assert "192.0.2.10" not in message
    assert "collector_error" in message
    assert populated_store.get_observation(3) is None


def test_forbidden_extra_fields_are_not_echoed(populated_store):
    with pytest.raises(ValueError) as captured:
        populated_store.save_observation(
            {
                "metadata": {
                    "observed_at": T0,
                    "source": ObservationSource.WINDOWS_HOST,
                    "scope": ObservationScope.AGGREGATE_GATEWAY,
                    "quality": ValueQuality.MEASURED,
                    "environment": ObservationEnvironment.PHYSICAL_HOST,
                },
                "mac_address": "00:11:22:33:44:55",
            }
        )

    message = str(captured.value)
    assert "00:11:22:33:44:55" not in message
    assert "mac_address" not in message
    assert message == "invalid observation"


def test_temporary_address_mapping_is_not_persisted(tmp_path):
    store = MetricsStore(tmp_path / "privacy.sqlite3")
    registry = AnonymousClientRegistry()
    client = registry.register()
    registry.associate_address(
        client.client_id,
        "temporary-address-1",
        now=T0,
    )
    store.register_client(
        client.client_id,
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )
    store.save_observation(
        TelemetryObservation(
            metadata={
                "observed_at": T0,
                "source": ObservationSource.LINUX_NAMESPACE_LAB,
                "scope": ObservationScope.CLIENT,
                "quality": ValueQuality.MEASURED,
                "environment": ObservationEnvironment.SIMULATED_LAB,
                "client_id": client.client_id,
            },
            download_mbps=0.0,
        )
    )

    values = all_values(store.db_path)
    assert "temporary-address-1" not in "\n".join(values)
    assert client.client_id in values


def test_anonymous_id_contains_no_hardware_identity(populated_store):
    client = populated_store.get_client(CLIENT_ID)

    assert client.client_id.startswith("client-")
    assert IPV4.search(client.client_id) is None
    assert MAC.search(client.client_id) is None
    assert client.environment == "simulated_lab"
    assert client.simulated_lab_slot == 1

import sqlite3
from datetime import datetime, timezone

import pytest

from network.telemetry.metrics_store import (
    MetricsStore,
    StoredAnonymousClient,
)


T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    return MetricsStore(tmp_path / "clients.sqlite3")


def test_register_get_and_list_clients_in_label_order(store):
    third = store.register_client("client-cccccccccccccccc", "Client 03")
    first = store.register_client("client-aaaaaaaaaaaaaaaa", "Client 01")
    second = store.register_client("client-bbbbbbbbbbbbbbbb", "Client 02")

    assert store.get_client(first.client_id).display_label == "Client 01"
    assert [client.client_id for client in store.list_clients()] == [
        first.client_id,
        second.client_id,
        third.client_id,
    ]
    assert all(
        client.environment == "physical_host" for client in store.list_clients()
    )


def test_duplicate_registration_is_idempotent(store):
    first = store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        first_seen_at=T0,
        last_seen_at=T0,
    )
    second = store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        first_seen_at=T0,
        last_seen_at=T0,
    )

    assert first == second
    assert len(store.list_clients()) == 1


def test_registration_merges_seen_timestamps(store):
    store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        first_seen_at=T0,
        last_seen_at=T0,
    )

    merged = store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        first_seen_at=T0.replace(hour=11),
        last_seen_at=T0.replace(hour=13),
    )

    assert merged.first_seen_at == T0.replace(hour=11)
    assert merged.last_seen_at == T0.replace(hour=13)


def test_conflicting_client_records_are_rejected(store):
    store.register_client("client-aaaaaaaaaaaaaaaa", "Client 01")

    with pytest.raises(ValueError, match="conflicting"):
        store.register_client("client-aaaaaaaaaaaaaaaa", "Client 02")

    with pytest.raises(ValueError, match="already assigned"):
        store.register_client("client-bbbbbbbbbbbbbbbb", "Client 01")

    store.register_client(
        "client-cccccccccccccccc",
        "Client 03",
        environment="simulated_lab",
        simulated_lab_slot=3,
    )
    with pytest.raises(ValueError, match="slot is already assigned"):
        store.register_client(
            "client-dddddddddddddddd",
            "Client 04",
            environment="simulated_lab",
            simulated_lab_slot=3,
        )


def test_simulated_lab_slot_survives_store_restart(tmp_path):
    path = tmp_path / "clients.sqlite3"
    first_store = MetricsStore(path)
    registered = first_store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )

    second_store = MetricsStore(path)
    recovered = second_store.get_simulated_client_by_slot(1)

    assert recovered == registered
    assert recovered.environment == "simulated_lab"
    assert recovered.simulated_lab_slot == 1
    assert second_store.get_simulated_client_by_slot(2) is None


def test_client_validation_rejects_identity_and_malformed_values(store):
    with pytest.raises(ValueError, match="anonymous client ID"):
        store.register_client("192.168.1.10", "Client 01")
    with pytest.raises(ValueError, match="display_label"):
        store.register_client("client-0123456789abcdef", "Laptop Alice")
    with pytest.raises(ValueError, match="environment"):
        store.register_client(
            "client-0123456789abcdef", "Client 01", environment="physical"
        )
    for slot in (True, 0, -1, 100):
        with pytest.raises(ValueError, match="simulated_lab_slot"):
            store.register_client(
                "client-0123456789abcdef",
                "Client 01",
                environment="simulated_lab",
                simulated_lab_slot=slot,
            )
    with pytest.raises(ValueError, match="simulated_lab_slot requires"):
        store.register_client(
            "client-0123456789abcdef", "Client 01", simulated_lab_slot=1
        )
    with pytest.raises(ValueError, match="timezone"):
        store.register_client(
            "client-0123456789abcdef",
            "Client 01",
            first_seen_at=datetime(2026, 11, 9, 12),
        )
    with pytest.raises(ValueError, match="must not follow"):
        store.register_client(
            "client-0123456789abcdef",
            "Client 01",
            first_seen_at=T0.replace(hour=13),
            last_seen_at=T0.replace(hour=12),
        )


def test_unknown_client_lookup_raises_keyerror(store):
    with pytest.raises(KeyError, match="unknown anonymous client"):
        store.get_client("client-0123456789abcdef")


def test_client_schema_has_no_identity_or_association_columns(store):
    connection = sqlite3.connect(store.db_path)

    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(anonymous_clients)"
            )
        }

    finally:
        connection.close()

    assert columns == {
        "client_id",
        "display_label",
        "environment",
        "simulated_lab_slot",
        "first_seen_at",
        "last_seen_at",
        "created_at",
    }
    forbidden = ("ip", "mac", "hostname", "device", "address", "url", "payload")
    assert not any(term in column.lower() for column in columns for term in forbidden)


def test_public_client_record_contains_only_allowed_fields(store):
    client = store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
        first_seen_at=T0,
        last_seen_at=T0,
    )

    assert isinstance(client, StoredAnonymousClient)
    public = client.model_dump(mode="json")
    assert set(public) == {
        "client_id",
        "display_label",
        "environment",
        "simulated_lab_slot",
        "first_seen_at",
        "last_seen_at",
    }
    serialized = str(public).lower()
    assert "192.168" not in serialized
    assert "mac" not in serialized
    assert "hostname" not in serialized
    assert "device" not in serialized
    assert "veth" not in serialized

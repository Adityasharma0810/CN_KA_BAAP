from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from backend.app.services.client_registry import (
    AnonymousClientRegistry,
    ClientStatus,
)


BASE_TIME = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def observation(client_id, observed_at=BASE_TIME, **extra):
    return TelemetryObservation(
        metadata={
            "observed_at": observed_at,
            "source": ObservationSource.LINUX_NAMESPACE_LAB,
            "scope": ObservationScope.CLIENT,
            "quality": ValueQuality.MEASURED,
            "environment": ObservationEnvironment.SIMULATED_LAB,
            "client_id": client_id,
        },
        download_bytes=extra.get("download_bytes", 10),
    )


def test_registers_unique_opaque_clients_with_stable_labels():
    registry = AnonymousClientRegistry()
    clients = [registry.register() for _ in range(3)]

    assert len({client.client_id for client in clients}) == 3
    assert [client.display_label for client in clients] == [
        "Client 01", "Client 02", "Client 03"
    ]
    assert all(client.client_id.startswith("client-") for client in clients)
    assert all(client.status == ClientStatus.UNKNOWN for client in clients)


def test_lookup_rejects_malformed_and_unknown_ids():
    registry = AnonymousClientRegistry()
    client = registry.register()

    assert registry.get(client.client_id).client_id == client.client_id
    with pytest.raises(ValueError, match="invalid anonymous"):
        registry.get("192.168.1.2")
    with pytest.raises(KeyError, match="unknown anonymous"):
        registry.get("client-0123456789abcdef")


def test_observation_updates_last_seen_and_status():
    registry = AnonymousClientRegistry(online_after=timedelta(seconds=30))
    client = registry.register()

    updated = registry.observe(observation(client.client_id))
    assert updated.status == ClientStatus.ONLINE
    assert updated.last_seen_at == BASE_TIME

    offline = registry.get(client.client_id, now=BASE_TIME + timedelta(seconds=31))
    assert offline.status == ClientStatus.OFFLINE

    stale = registry.get(client.client_id, now=BASE_TIME + timedelta(minutes=6))
    assert stale.status == ClientStatus.OFFLINE
    assert stale.stale is True


def test_unknown_client_stays_unknown_until_observed():
    registry = AnonymousClientRegistry()
    client = registry.register()
    result = registry.get(client.client_id, now=BASE_TIME + timedelta(days=1))

    assert result.status == ClientStatus.UNKNOWN
    assert result.stale is False


def test_explicit_offline_and_reconnection():
    registry = AnonymousClientRegistry()
    client = registry.register()
    registry.observe(observation(client.client_id))
    assert registry.mark_offline(client.client_id).status == ClientStatus.OFFLINE

    reconnected = registry.observe(
        observation(client.client_id, BASE_TIME + timedelta(seconds=5))
    )
    assert reconnected.status == ClientStatus.ONLINE


def test_rejects_invalid_or_out_of_order_observations():
    registry = AnonymousClientRegistry()
    client = registry.register()

    with pytest.raises(ValueError, match="client observation"):
        registry.observe(
            TelemetryObservation(
                metadata={
                    "observed_at": BASE_TIME,
                    "source": ObservationSource.WINDOWS_HOST,
                    "scope": ObservationScope.AGGREGATE_GATEWAY,
                    "quality": ValueQuality.MEASURED,
                    "environment": ObservationEnvironment.PHYSICAL_HOST,
                }
            )
        )

    registry.observe(observation(client.client_id))
    with pytest.raises(ValueError, match="precedes"):
        registry.observe(observation(client.client_id, BASE_TIME - timedelta(seconds=1)))


def test_address_associations_are_private_and_collision_safe():
    registry = AnonymousClientRegistry()
    first = registry.register()
    second = registry.register()
    address = "temporary-address-1"

    registry.associate_address(first.client_id, address, now=BASE_TIME)
    assert registry.lookup_address(address, now=BASE_TIME) == first.client_id
    with pytest.raises(ValueError, match="already associated"):
        registry.associate_address(second.client_id, address, now=BASE_TIME)

    public = registry.public_snapshot()
    assert address not in str(public)
    assert all("ip" not in field.lower() and "mac" not in field.lower() for field in public[0])


def test_expired_associations_are_removed_without_removing_clients():
    registry = AnonymousClientRegistry(association_after=timedelta(seconds=10))
    client = registry.register()
    registry.associate_address(client.client_id, "temporary", now=BASE_TIME)

    assert registry.cleanup_expired(now=BASE_TIME + timedelta(seconds=11)) == 1
    assert registry.lookup_address("temporary", now=BASE_TIME + timedelta(seconds=11)) is None
    assert registry.get(client.client_id).client_id == client.client_id


def test_remove_cleans_client_and_associations():
    registry = AnonymousClientRegistry()
    client = registry.register()
    registry.associate_address(client.client_id, "temporary", now=BASE_TIME)
    registry.remove(client.client_id)

    assert registry.lookup_address("temporary", now=BASE_TIME) is None
    with pytest.raises(KeyError):
        registry.get(client.client_id)


def test_reset_clears_runtime_state_but_only_registry_data():
    registry = AnonymousClientRegistry()
    client = registry.register()
    registry.associate_address(client.client_id, "temporary", now=BASE_TIME)
    registry.reset()

    assert registry.list_clients() == []
    assert registry.lookup_address("temporary", now=BASE_TIME) is None
    new_client = registry.register()
    assert new_client.display_label == "Client 01"


def test_public_representation_has_no_forbidden_identity_fields():
    registry = AnonymousClientRegistry()
    client = registry.register()
    registry.observe(observation(client.client_id))
    public = registry.get(client.client_id).model_dump()

    assert set(public) == {
        "client_id", "display_label", "status", "first_seen_at", "last_seen_at", "stale"
    }
    serialized = str(public).lower()
    assert "ip" not in serialized
    assert "mac" not in serialized
    assert "device" not in serialized


def test_concurrent_registration_produces_unique_clients():
    registry = AnonymousClientRegistry()
    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(lambda _: registry.register(), range(32)))

    assert len({client.client_id for client in clients}) == 32
    assert len(registry.list_clients()) == 32


def test_registry_validates_configuration_and_naive_times():
    with pytest.raises(ValueError):
        AnonymousClientRegistry(online_after=timedelta(seconds=10), offline_after=timedelta(seconds=1))

    registry = AnonymousClientRegistry()
    client = registry.register()
    with pytest.raises(ValueError, match="timezone"):
        registry.associate_address(client.client_id, "temporary", now=datetime(2026, 11, 9, 12))

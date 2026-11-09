from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from network.telemetry.metrics_store import MAX_HISTORY_LIMIT, MetricsStore


T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
CLIENT_ONE = "client-aaaaaaaaaaaaaaaa"
CLIENT_TWO = "client-bbbbbbbbbbbbbbbb"


@pytest.fixture
def store(tmp_path):
    database = MetricsStore(tmp_path / "history.sqlite3")
    database.register_client(
        CLIENT_ONE,
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )
    database.register_client(
        CLIENT_TWO,
        "Client 02",
        environment="simulated_lab",
        simulated_lab_slot=2,
    )

    database.save_observations(
        [
            observation(
                T0,
                source=ObservationSource.WINDOWS_HOST,
                scope=ObservationScope.AGGREGATE_GATEWAY,
                environment=ObservationEnvironment.PHYSICAL_HOST,
                download_mbps=10.0,
            ),
            observation(
                T0 + timedelta(seconds=1),
                source=ObservationSource.WINDOWS_HOTSPOT,
                scope=ObservationScope.AGGREGATE_HOTSPOT,
                environment=ObservationEnvironment.PHYSICAL_HOST,
                download_mbps=20.0,
            ),
            observation(
                T0 + timedelta(seconds=2),
                source=ObservationSource.LINUX_NAMESPACE_LAB,
                scope=ObservationScope.CLIENT,
                environment=ObservationEnvironment.SIMULATED_LAB,
                client_id=CLIENT_ONE,
                download_mbps=1.0,
            ),
            observation(
                T0 + timedelta(seconds=3),
                source=ObservationSource.LINUX_NAMESPACE_LAB,
                scope=ObservationScope.CLIENT,
                environment=ObservationEnvironment.SIMULATED_LAB,
                client_id=CLIENT_TWO,
                download_mbps=2.0,
            ),
            observation(
                T0 + timedelta(seconds=4),
                source=ObservationSource.LINUX_NAMESPACE_LAB,
                scope=ObservationScope.CLIENT,
                environment=ObservationEnvironment.SIMULATED_LAB,
                client_id=CLIENT_ONE,
                download_mbps=3.0,
            ),
        ]
    )
    return database


def observation(
    observed_at,
    *,
    source,
    scope,
    environment,
    client_id=None,
    download_mbps=0.0,
):
    return TelemetryObservation(
        metadata={
            "observed_at": observed_at,
            "source": source,
            "scope": scope,
            "quality": ValueQuality.MEASURED,
            "environment": environment,
            "client_id": client_id,
        },
        download_mbps=download_mbps,
    )


def test_aggregate_history_excludes_per_client_rows(store):
    history = store.get_aggregate_history(limit=100)

    assert len(history) == 2
    assert {item.observation.metadata.scope for item in history} == {
        "aggregate_gateway",
        "aggregate_hotspot",
    }
    assert all(item.observation.metadata.client_id is None for item in history)
    assert store.count_observations(aggregate_only=True) == 2


def test_client_history_is_strictly_isolated(store):
    first = store.get_client_history(CLIENT_ONE, limit=100)
    second = store.get_client_history(CLIENT_TWO, limit=100)

    assert len(first) == 2
    assert len(second) == 1
    assert {item.observation.metadata.client_id for item in first} == {CLIENT_ONE}
    assert {item.observation.metadata.client_id for item in second} == {CLIENT_TWO}
    assert {item.observation.download_mbps for item in first} == {1.0, 3.0}
    assert {item.observation.download_mbps for item in second} == {2.0}


def test_query_by_source_environment_and_scope(store):
    hotspot = store.get_history_by_source("windows_hotspot")
    clients = store.get_history_by_source(
        ObservationSource.LINUX_NAMESPACE_LAB
    )
    simulated = store.query_history(environment="simulated_lab")
    aggregate_gateway = store.query_history(scope="aggregate_gateway")
    client_scope = store.query_history(scope="client")

    assert len(hotspot) == 1
    assert hotspot[0].observation.metadata.scope == "aggregate_hotspot"
    assert len(clients) == 3
    assert all(
        item.observation.metadata.source == "linux_namespace_lab"
        for item in clients
    )
    assert len(simulated) == 3
    assert all(
        item.observation.metadata.environment == "simulated_lab"
        for item in simulated
    )
    assert len(aggregate_gateway) == 1
    assert len(client_scope) == 3


def test_time_range_is_inclusive(store):
    window = store.query_history(
        start=T0,
        end=T0 + timedelta(seconds=1),
        order="oldest",
    )
    exact = store.query_history(start=T0, end=T0)
    empty = store.query_history(
        start=T0 + timedelta(seconds=10),
        end=T0 + timedelta(seconds=20),
    )

    assert [item.observation.metadata.observed_at for item in window] == [
        T0,
        T0 + timedelta(seconds=1),
    ]
    assert len(exact) == 1
    assert empty == []


def test_sorting_is_deterministic_for_identical_timestamps(store):
    same_time = T0 + timedelta(seconds=10)
    ids = store.save_observations(
        [
            observation(
                same_time,
                source=ObservationSource.WINDOWS_HOST,
                scope=ObservationScope.AGGREGATE_GATEWAY,
                environment=ObservationEnvironment.PHYSICAL_HOST,
                download_mbps=30.0,
            ),
            observation(
                same_time,
                source=ObservationSource.WINDOWS_HOST,
                scope=ObservationScope.AGGREGATE_GATEWAY,
                environment=ObservationEnvironment.PHYSICAL_HOST,
                download_mbps=40.0,
            ),
        ]
    )

    oldest = store.query_history(
        start=same_time,
        end=same_time,
        order="oldest",
    )
    newest = store.query_history(
        start=same_time,
        end=same_time,
        order="newest",
    )

    assert [item.id for item in oldest] == ids
    assert [item.id for item in newest] == list(reversed(ids))
    assert [item.observation.download_mbps for item in oldest] == [30.0, 40.0]


def test_pagination_is_bounded_and_ordered(store):
    first = store.query_history(limit=2, offset=0, order="oldest")
    second = store.query_history(limit=2, offset=2, order="oldest")
    beyond = store.query_history(limit=2, offset=100, order="oldest")

    assert len(first) == 2
    assert len(second) == 2
    assert beyond == []
    assert first[0].id < second[0].id


def test_count_matches_filters(store):
    assert store.count_observations() == 5
    assert store.count_observations(client_id=CLIENT_ONE) == 2
    assert store.count_observations(source="windows_hotspot") == 1
    assert store.count_observations(environment="simulated_lab") == 3
    assert (
        store.count_observations(
            start=T0,
            end=T0 + timedelta(seconds=1),
        )
        == 2
    )


def test_invalid_query_arguments_are_rejected(store):
    with pytest.raises(ValueError, match="start must not follow end"):
        store.query_history(
            start=T0 + timedelta(seconds=2),
            end=T0,
        )
    for limit in (0, -1, MAX_HISTORY_LIMIT + 1, True, "10"):
        with pytest.raises(ValueError, match="limit"):
            store.query_history(limit=limit)
    for offset in (-1, True, "0"):
        with pytest.raises(ValueError, match="offset"):
            store.query_history(offset=offset)
    with pytest.raises(ValueError, match="order"):
        store.query_history(order="random")
    with pytest.raises(ValueError, match="scope"):
        store.query_history(scope="everything")
    with pytest.raises(ValueError, match="source"):
        store.query_history(source="device")
    with pytest.raises(ValueError, match="environment"):
        store.query_history(environment="home")
    with pytest.raises(ValueError, match="anonymous client ID"):
        store.query_history(client_id="192.168.1.2")
    with pytest.raises(ValueError, match="client scope"):
        store.get_aggregate_history(scope="client")
    with pytest.raises(ValueError, match="client_id requires client scope"):
        store.query_history(
            scope="aggregate_gateway",
            client_id=CLIENT_ONE,
        )
    with pytest.raises(ValueError, match="client scope"):
        store.query_history(
            client_id=CLIENT_ONE,
            aggregate_only=True,
        )
    with pytest.raises(ValueError, match="ISO 8601"):
        store.query_history(start="not-a-timestamp")


def test_history_returns_shared_observation_models(store):
    history = store.get_client_history(CLIENT_ONE)

    assert history
    assert all(
        isinstance(item.observation, TelemetryObservation) for item in history
    )
    assert history[0].observation.metadata.client_id == CLIENT_ONE


def test_aggregate_and_client_queries_cannot_mix(store):
    aggregate_ids = {item.id for item in store.get_aggregate_history(limit=100)}
    client_ids = {
        item.id for item in store.query_history(scope="client", limit=100)
    }

    assert aggregate_ids.isdisjoint(client_ids)
    assert store.count_observations(aggregate_only=True) == 2
    assert store.count_observations(scope="client") == 3

from datetime import datetime, timedelta, timezone

import pytest

import backend.app.services.topology_service as topology_service_module
from backend.app.models.schemas import TelemetryObservation
from backend.app.models.topology_schemas import (
    TopologyEdgeType,
    TopologyLink,
    TopologyNode,
    TopologyNodeKind,
    TopologySource,
    TopologyState,
)
from backend.app.services.client_registry import AnonymousClientRegistry
from backend.app.services.lab_accounting_service import lab_accounting_service
from backend.app.services.topology_service import (
    TopologyService,
    TopologyValidationError,
    validate_edges,
)
from network.telemetry.metrics_store import MetricsStore


NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _observation(
    source: str = "windows_host",
    scope: str = "aggregate_gateway",
    *,
    observed_at: datetime = NOW,
    quality: str = "measured",
    client_id: str | None = None,
) -> TelemetryObservation:
    return TelemetryObservation(
        metadata={
            "observed_at": observed_at,
            "source": source,
            "scope": scope,
            "quality": quality,
            "environment": "simulated_lab" if scope == "client" else "physical_host",
            "client_id": client_id,
        },
        download_mbps=1.0,
    )


def _service(tmp_path, registry=None):
    path = tmp_path / "topology.sqlite3"
    store = MetricsStore(path)
    service = TopologyService(
        db_path=path,
        clock=lambda: NOW,
        registry=registry or AnonymousClientRegistry(),
    )
    return service, store


def test_empty_database_has_online_application_and_missing_sources(tmp_path):
    service, _ = _service(tmp_path)

    status = service.gateway_status()
    topology = service.network_topology()

    assert status.application.state == TopologyState.ONLINE
    assert {
        status.windows_host.state,
        status.hotspot.state,
        status.linux_lab.state,
    } == {TopologyState.MISSING}
    assert topology.nodes[0].state == TopologyState.ONLINE
    assert {node.state for node in topology.nodes[1:]} == {
        TopologyState.MISSING
    }
    assert topology.links == []


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(seconds=299), TopologyState.ONLINE),
        (timedelta(seconds=300), TopologyState.ONLINE),
        (timedelta(seconds=301), TopologyState.STALE),
    ],
)
def test_source_freshness_uses_shared_threshold(tmp_path, age, expected):
    service, store = _service(tmp_path)
    store.save_observation(
        _observation(observed_at=NOW - age)
    )

    result = service.gateway_status().windows_host

    assert result.state == expected


def test_fresh_unknown_quality_remains_unknown(tmp_path):
    service, store = _service(tmp_path)
    store.save_observation(_observation(quality="unknown"))

    result = service.gateway_status().windows_host

    assert result.state == TopologyState.UNKNOWN
    assert result.data_quality == "unknown"


def test_explicitly_offline_registry_client_is_offline(tmp_path):
    registry = AnonymousClientRegistry()
    registered = registry.register()
    service, store = _service(tmp_path, registry)
    observation = _observation(
        "linux_namespace_lab",
        "client",
        client_id=registered.client_id,
    )
    store.register_client(
        registered.client_id,
        registered.display_label,
        environment="simulated_lab",
        simulated_lab_slot=1,
    )
    store.save_observation(observation)
    registry.observe(observation, now=NOW)
    registry.mark_offline(registered.client_id, now=NOW)

    client_node = next(
        node for node in service.network_topology().nodes
        if node.kind == TopologyNodeKind.CLIENT
    )

    assert client_node.state == TopologyState.OFFLINE
    assert client_node.data_quality == "measured"


def test_unavailable_quality_is_not_misreported_as_offline(tmp_path):
    service, store = _service(tmp_path)
    store.save_observation(
        _observation(quality="unavailable")
    )

    status = service.gateway_status().windows_host

    assert status.state == TopologyState.UNAVAILABLE
    assert status.state != TopologyState.OFFLINE


def test_source_failure_isolated_from_other_sources(
    monkeypatch, tmp_path
):
    service, store = _service(tmp_path)
    store.save_observation(
        _observation("windows_hotspot", "aggregate_hotspot")
    )
    original = topology_service_module.build_current_observations

    def fail_host(*args, **kwargs):
        if kwargs.get("source") == "windows_host":
            raise RuntimeError("private source detail")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        topology_service_module,
        "build_current_observations",
        fail_host,
    )

    status = service.gateway_status()

    assert status.windows_host.state == TopologyState.UNAVAILABLE
    assert status.hotspot.state == TopologyState.ONLINE
    assert status.linux_lab.state == TopologyState.MISSING


def test_linux_lab_failure_is_unavailable_without_affecting_other_sources(
    monkeypatch, tmp_path
):
    service, store = _service(tmp_path)
    store.register_client(
        "client-0123456789abcdef",
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )
    store.save_observation(
        _observation(
            "linux_namespace_lab",
            "client",
            client_id="client-0123456789abcdef",
        )
    )
    original = topology_service_module.build_current_observations

    def fail_linux_gateway(*args, **kwargs):
        if kwargs.get("source") == "linux_gateway":
            raise RuntimeError("linux aggregate query failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        topology_service_module,
        "build_current_observations",
        fail_linux_gateway,
    )

    status = service.gateway_status()

    assert status.linux_lab.state == TopologyState.UNAVAILABLE
    assert status.application.state == TopologyState.ONLINE
    assert status.windows_host.state == TopologyState.MISSING
    assert status.hotspot.state == TopologyState.MISSING


def test_registry_failure_isolated_and_live_probe_is_never_called(
    monkeypatch, tmp_path
):
    service, store = _service(tmp_path)
    store.save_observation(_observation())
    monkeypatch.setattr(
        lab_accounting_service,
        "collect",
        lambda: (_ for _ in ()).throw(AssertionError("live probe called")),
    )
    monkeypatch.setattr(
        service.registry,
        "list_clients",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("private detail")),
    )

    topology = service.network_topology()

    states = {item.source: item.state for item in topology.sources}
    assert states[TopologySource.ANONYMOUS_REGISTRY.value] == "unavailable"
    assert states[TopologySource.WINDOWS_HOST.value] == "online"
    assert "private detail" not in str(topology.model_dump())


def _node(node_id):
    return TopologyNode(
        node_id=node_id,
        kind=TopologyNodeKind.APPLICATION,
        label="Application",
        state=TopologyState.MISSING,
        source=TopologySource.APPLICATION,
        data_quality="unknown",
    )


@pytest.mark.parametrize(
    ("nodes", "edges"),
    [
        (
            [_node("one")],
            [
                TopologyLink(
                    source="one",
                    target="missing",
                    relation=TopologyEdgeType.UNKNOWN,
                )
            ],
        ),
        (
            [_node("one"), _node("two")],
            [
                TopologyLink(
                    source="one",
                    target="two",
                    relation=TopologyEdgeType.OBSERVED,
                ),
                TopologyLink(
                    source="two",
                    target="one",
                    relation=TopologyEdgeType.DERIVED,
                ),
            ],
        ),
        (
            [_node("one")],
            [
                TopologyLink(
                    source="one",
                    target="one",
                    relation=TopologyEdgeType.UNKNOWN,
                )
            ],
        ),
    ],
)
def test_edge_validator_rejects_invalid_edges(nodes, edges):
    with pytest.raises(TopologyValidationError):
        validate_edges(nodes, edges)


def test_edge_validator_accepts_unique_edges():
    nodes = [_node("lab"), _node("client-01")]
    edges = [
        TopologyLink(
            source="lab",
            target="client-01",
            relation=TopologyEdgeType.OBSERVED,
        )
    ]

    validate_edges(nodes, edges)


def test_extra_node_fields_are_forbidden():
    with pytest.raises(ValueError):
        TopologyNode.model_validate(
            {
                "node_id": "application",
                "kind": "application",
                "label": "Application",
                "state": "missing",
                "source": "application",
                "data_quality": "unknown",
                "ip": "192.0.2.1",
            }
        )

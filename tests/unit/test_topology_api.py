from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import backend.app.api.topology as topology_api
import backend.app.services.topology_service as topology_service_module
from backend.app.main import app
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
from backend.app.services.topology_service import TopologyService
from network.telemetry.metrics_store import MetricsStore


client = TestClient(app)
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _observation(
    source: str,
    scope: str,
    *,
    observed_at: datetime = NOW,
    quality: str = "measured",
    client_id: str | None = None,
) -> TelemetryObservation:
    environment = "simulated_lab" if scope == "client" else "physical_host"
    return TelemetryObservation(
        metadata={
            "observed_at": observed_at,
            "source": source,
            "scope": scope,
            "quality": quality,
            "environment": environment,
            "client_id": client_id,
        },
        download_mbps=1.25,
    )


def _configure(monkeypatch, tmp_path):
    path = tmp_path / "topology.sqlite3"
    store = MetricsStore(path)
    registry = AnonymousClientRegistry()
    service = TopologyService(
        db_path=path,
        clock=lambda: NOW,
        registry=registry,
    )
    monkeypatch.setattr(topology_api, "topology_service", service)
    monkeypatch.setattr(
        lab_accounting_service,
        "collect",
        lambda: (_ for _ in ()).throw(AssertionError("live probe called")),
    )
    return store, registry


def test_empty_database_reports_all_nodes_missing(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)

    status = client.get("/api/v1/gateway/status")
    topology = client.get("/api/v1/network/topology")

    assert status.status_code == 200
    status_body = status.json()
    assert set(status_body) == {
        "observed_at",
        "application",
        "windows_host",
        "hotspot",
        "linux_lab",
    }
    assert {
        name: item["state"]
        for name, item in status_body.items()
        if name != "observed_at"
    } == {
        "application": "missing",
        "windows_host": "missing",
        "hotspot": "missing",
        "linux_lab": "missing",
    }
    assert all(
        item["last_observed_at"] is None
        and item["data_quality"] == "unknown"
        for name, item in status_body.items()
        if name != "observed_at"
    )

    assert topology.status_code == 200
    topology_body = topology.json()
    assert [node["node_id"] for node in topology_body["nodes"]] == [
        "application",
        "windows-host",
        "hotspot-aggregate",
        "linux-lab",
    ]
    assert all(node["state"] == "missing" for node in topology_body["nodes"])
    assert topology_body["links"] == []


@pytest.mark.parametrize(
    ("age", "expected_state"),
    [
        (timedelta(seconds=299), "unknown"),
        (timedelta(seconds=300), "unknown"),
        (timedelta(seconds=301), "stale"),
    ],
)
def test_gateway_status_freshness_boundary(
    monkeypatch, tmp_path, age, expected_state
):
    store, _ = _configure(monkeypatch, tmp_path)
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            observed_at=NOW - age,
        )
    )

    response = client.get("/api/v1/gateway/status")

    assert response.status_code == 200
    host = response.json()["windows_host"]
    assert host["state"] == expected_state
    assert host["data_quality"] == "measured"
    assert host["last_observed_at"] == (
        NOW - age
    ).isoformat().replace("+00:00", "Z")


def test_client_offline_state_comes_from_explicit_registry_status(
    monkeypatch, tmp_path
):
    store, registry = _configure(monkeypatch, tmp_path)
    registered = registry.register()
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

    response = client.get("/api/v1/network/topology")

    assert response.status_code == 200
    node = next(
        node for node in response.json()["nodes"] if node["kind"] == "client"
    )
    assert node["state"] == "offline"
    assert node["data_quality"] == "measured"
    assert node["client_id"] == registered.client_id


def test_source_failure_is_isolated_and_not_exposed(
    monkeypatch, tmp_path
):
    store, _ = _configure(monkeypatch, tmp_path)
    store.save_observation(
        _observation("windows_hotspot", "aggregate_hotspot")
    )
    original = topology_service_module.build_current_observations

    def fail_windows_host(*args, **kwargs):
        if kwargs.get("source") == "windows_host":
            raise RuntimeError("private source path")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        topology_service_module,
        "build_current_observations",
        fail_windows_host,
    )

    response = client.get("/api/v1/gateway/status")

    assert response.status_code == 200
    body = response.json()
    assert body["windows_host"]["state"] == "unavailable"
    assert body["windows_host"]["data_quality"] == "unavailable"
    assert body["hotspot"]["state"] == "unknown"
    assert body["linux_lab"]["state"] == "missing"
    assert "private source path" not in response.text


def test_hotspot_and_lab_coexist_without_aggregate_client_attribution(
    monkeypatch, tmp_path
):
    store, registry = _configure(monkeypatch, tmp_path)
    registered = registry.register()
    store.register_client(
        registered.client_id,
        registered.display_label,
        environment="simulated_lab",
        simulated_lab_slot=1,
    )
    store.save_observation(
        _observation("windows_host", "aggregate_gateway")
    )
    store.save_observation(
        _observation("windows_hotspot", "aggregate_hotspot")
    )
    client_observation = _observation(
        "linux_namespace_lab",
        "client",
        client_id=registered.client_id,
    )
    store.save_observation(client_observation)
    registry.observe(client_observation, now=NOW)

    response = client.get("/api/v1/network/topology")

    assert response.status_code == 200
    body = response.json()
    nodes = body["nodes"]
    assert {node["kind"] for node in nodes} == {
        "application",
        "windows_host",
        "hotspot",
        "linux_lab",
        "client",
    }
    assert not any(node["node_id"] == "router" for node in nodes)
    client_nodes = [node for node in nodes if node["kind"] == "client"]
    assert len(client_nodes) == 1
    assert client_nodes[0]["label"] == "Client 01"
    assert client_nodes[0]["client_id"] == registered.client_id
    assert body["links"] == [
        {
            "source": "linux-lab",
            "target": "client-01",
            "relation": "observed",
        }
    ]


def test_registry_failure_does_not_change_other_sources(
    monkeypatch, tmp_path
):
    store, _ = _configure(monkeypatch, tmp_path)
    store.save_observation(
        _observation("windows_host", "aggregate_gateway")
    )

    def fail_registry(*, now=None):
        raise RuntimeError("registry private detail")

    monkeypatch.setattr(
        topology_api.topology_service.registry,
        "list_clients",
        fail_registry,
    )
    response = client.get("/api/v1/network/topology")

    assert response.status_code == 200
    body = response.json()
    source_states = {source["source"]: source["state"] for source in body["sources"]}
    assert source_states["anonymous_registry"] == "unavailable"
    assert source_states["windows_host"] == "unknown"
    assert "registry private detail" not in response.text


def test_topology_is_private_and_openapi_is_typed(monkeypatch, tmp_path):
    store, _ = _configure(monkeypatch, tmp_path)
    store.save_observation(
        _observation("windows_host", "aggregate_gateway")
    )

    response = client.get("/api/v1/network/topology")

    assert response.status_code == 200
    lowered = response.text.lower()
    for forbidden in (
        "ip",
        "mac",
        "hostname",
        "namespace",
        "veth",
        "bridge",
        "adapter",
    ):
        assert forbidden not in lowered
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/v1/gateway/status"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GatewayStatusResponse"
    }
    assert schema["paths"]["/api/v1/network/topology"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TopologyResponse"
    }


def test_topology_schemas_forbid_extra_fields_and_free_text_states():
    with pytest.raises(ValidationError):
        TopologyNode(
            node_id="application",
            kind=TopologyNodeKind.APPLICATION,
            label="Application",
            state=TopologyState.MISSING,
            source=TopologySource.APPLICATION,
            data_quality="unknown",
            hostname="private",
        )
    with pytest.raises(ValidationError):
        TopologyLink(
            source="linux-lab",
            target="client-01",
            relation="physical cable",
        )


def test_topology_validation_failure_returns_safe_service_unavailable(
    monkeypatch, tmp_path
):
    _configure(monkeypatch, tmp_path)

    def reject_edges(nodes, edges):
        raise topology_service_module.TopologyValidationError(
            "dangling node contains private detail"
        )

    monkeypatch.setattr(topology_service_module, "validate_edges", reject_edges)
    response = client.get("/api/v1/network/topology")

    assert response.status_code == 503
    assert response.json() == {"detail": "topology_unavailable"}
    assert "private detail" not in response.text

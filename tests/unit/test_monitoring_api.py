
from fastapi.testclient import TestClient

import backend.app.api.monitoring as monitoring_api
from backend.app.main import app
from network.telemetry.metrics_store import MetricsStore


client = TestClient(app)


def test_versioned_health_endpoint(monkeypatch, tmp_path):
    database_path = tmp_path / "health.sqlite3"
    MetricsStore(database_path)
    monkeypatch.setenv("EB_DATABASE_PATH", str(database_path))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "observed_at", "components"}
    assert body["status"] == "degraded"
    assert isinstance(body["observed_at"], str)
    assert isinstance(body["components"], dict)
    assert set(body["components"]) == {
        "application",
        "database",
        "windows_host_collector",
        "windows_hotspot_collector",
        "gateway",
        "client_registry",
    }
    assert all(
        isinstance(component, dict) and isinstance(component["status"], str)
        for component in body["components"].values()
    )
    assert {
        name: component["status"]
        for name, component in body["components"].items()
    } == {
        "application": "healthy",
        "database": "healthy",
        "windows_host_collector": "unavailable",
        "windows_hotspot_collector": "unavailable",
        "gateway": "unavailable",
        "client_registry": "healthy",
    }
    assert body["components"]["database"]["schema_version"] == 1
    assert isinstance(body["components"]["client_registry"]["client_count"], int)
    assert "ip" not in response.text.lower()
    assert "mac" not in response.text.lower()


def test_collector_health_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("EB_DATABASE_PATH", str(tmp_path / "health.sqlite3"))

    response = client.get("/api/v1/health/collectors")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"observed_at", "collectors"}
    assert isinstance(body["observed_at"], str)
    assert [collector["collector"] for collector in body["collectors"]] == [
        "windows_host",
        "windows_hotspot",
        "linux_gateway",
    ]
    assert all(
        collector["status"] == "unavailable" and collector["stale"] is False
        for collector in body["collectors"]
    )


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["mode"] == "baseline_monitoring"


def test_collect_endpoint(monkeypatch):
    expected = {
        "sample_id": 1,
        "interface": "Wi-Fi",
        "scope": "local_aggregate_only",
    }

    def fake_collect_and_store(**kwargs):
        assert kwargs["adapter"] == "Wi-Fi"
        return expected

    monkeypatch.setattr(
        monitoring_api,
        "collect_and_store",
        fake_collect_and_store,
    )

    response = client.post(
        "/api/v1/monitoring/collect",
        json={},
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_reject_unapproved_probe_target():
    response = client.post(
        "/api/v1/monitoring/collect",
        json={"quality_target": "192.168.1.1"},
    )

    assert response.status_code == 422


def test_lab_clients_endpoint(monkeypatch):
    expected = {
        "available": True,
        "source": "linux_namespace_lab",
        "environment": "simulated_lab",
        "scope": "client",
        "clients": [],
    }
    monkeypatch.setattr(monitoring_api.lab_accounting_service, "collect", lambda: expected)

    response = client.get("/api/v1/monitoring/lab/clients")

    assert response.status_code == 200
    assert response.json() == expected


def test_history_endpoint(monkeypatch):
    expected = [{"id": 1, "download_mbps": 12.5}]

    monkeypatch.setattr(
        monitoring_api,
        "get_history",
        lambda limit: expected,
    )

    response = client.get(
        "/api/v1/monitoring/history?limit=10"
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["samples"] == expected


def test_history_limit_validation():
    response = client.get(
        "/api/v1/monitoring/history?limit=1000"
    )

    assert response.status_code == 422

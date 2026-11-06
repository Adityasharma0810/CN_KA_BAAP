
from fastapi.testclient import TestClient

import backend.app.api.monitoring as monitoring_api
from backend.app.main import app


client = TestClient(app)


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

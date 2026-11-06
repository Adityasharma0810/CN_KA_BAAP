
from fastapi.testclient import TestClient

import backend.app.api.monitoring as monitoring_api
from backend.app.main import app

client = TestClient(app)


def test_hotspot_collection(monkeypatch):

    expected = {
        "sample_id": 10,
        "download_mbps": 2.5,
        "upload_mbps": 0.5,
        "scope": "anonymous_downstream_aggregate",
    }

    monkeypatch.setattr(
        monitoring_api,
        "collect_hotspot_and_store",
        lambda **kwargs: expected,
    )

    response = client.post(
        "/api/v1/monitoring/hotspot/collect",
        json={"sample_interval_seconds": 1},
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_hotspot_history(monkeypatch):

    expected = [
        {
            "id": 10,
            "interface_label": "hotspot-aggregate",
            "download_mbps": 2.5,
            "upload_mbps": 0.5,
        }
    ]

    monkeypatch.setattr(
        monitoring_api,
        "get_hotspot_history",
        lambda limit: expected,
    )

    response = client.get(
        "/api/v1/monitoring/hotspot/history?limit=10"
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["samples"] == expected


def test_hotspot_collection_validation():

    response = client.post(
        "/api/v1/monitoring/hotspot/collect",
        json={"sample_interval_seconds": 10},
    )

    assert response.status_code == 422

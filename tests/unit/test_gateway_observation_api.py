from datetime import datetime, timezone

from fastapi.testclient import TestClient

import gateway.observation_api as agent


NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def client_observation(client_id="client-abcdefgh"):
    return {
        "metadata": {
            "observed_at": NOW.isoformat(),
            "source": "linux_namespace_lab",
            "scope": "client",
            "quality": "measured",
            "environment": "simulated_lab",
            "client_id": client_id,
        },
        "download_mbps": 5.0,
        "upload_mbps": 1.0,
    }


def set_collection(monkeypatch, collection):
    monkeypatch.setattr(agent.lab_accounting_service, "collect", lambda: collection)
    monkeypatch.setenv("EB_GATEWAY_TOKEN", "test-token")


def test_current_observations_returns_only_validated_lab_observations(monkeypatch):
    set_collection(
        monkeypatch,
        {
            "available": True,
            "clients": [{"observation": client_observation()}],
        },
    )

    response = TestClient(agent.app).get(
        "/api/v1/observations/current",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["observations"][0]["metadata"]["client_id"] == "client-abcdefgh"
    assert body["observations"][0]["metadata"]["environment"] == "simulated_lab"
    assert set(agent.app.openapi()["paths"]) == {"/api/v1/observations/current"}


def test_missing_and_invalid_tokens_are_rejected(monkeypatch):
    set_collection(monkeypatch, {"available": True, "clients": []})
    client = TestClient(agent.app)

    missing = client.get("/api/v1/observations/current")
    invalid = client.get(
        "/api/v1/observations/current",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["detail"] == "gateway_authentication_failed"
    assert invalid.json()["detail"] == "gateway_authentication_failed"


def test_missing_gateway_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("EB_GATEWAY_TOKEN", raising=False)

    response = TestClient(agent.app).get("/api/v1/observations/current")

    assert response.status_code == 503
    assert response.json()["detail"] == "gateway_authentication_not_configured"


def test_unavailable_lab_is_not_returned_as_zero_traffic(monkeypatch):
    set_collection(
        monkeypatch,
        {
            "available": False,
            "clients": [],
        },
    )

    response = TestClient(agent.app).get(
        "/api/v1/observations/current",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "gateway_lab_unavailable"


def test_invalid_or_duplicate_identity_inventory_is_rejected(monkeypatch):
    set_collection(
        monkeypatch,
        {
            "available": True,
            "clients": [
                {"observation": client_observation()},
                {"observation": client_observation()},
            ],
        },
    )

    response = TestClient(agent.app).get(
        "/api/v1/observations/current",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "gateway_observation_unavailable"

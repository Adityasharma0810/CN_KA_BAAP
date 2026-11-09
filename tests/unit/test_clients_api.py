from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.schemas import TelemetryObservation
from backend.app.services.lab_accounting_service import lab_accounting_service


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    lab_accounting_service.registry.reset()
    yield
    lab_accounting_service.registry.reset()


def _observation(client_id: str, *, observed_at=None, download=10.0):
    return TelemetryObservation(
        metadata={
            "observed_at": observed_at or datetime.now(timezone.utc),
            "source": "linux_namespace_lab",
            "scope": "client",
            "quality": "measured",
            "environment": "simulated_lab",
            "client_id": client_id,
        },
        download_mbps=download,
        upload_mbps=1.0,
    ).model_dump(mode="json")


def _available_result(observations):
    return {
        "available": True,
        "source": "linux_namespace_lab",
        "environment": "simulated_lab",
        "scope": "client",
        "clients": [
            {"client_id": client_id, "observation": observation}
            for client_id, observation in observations.items()
        ],
    }


def test_three_client_listing_returns_all_registered_clients(monkeypatch):
    registered = [lab_accounting_service.registry.register() for _ in range(3)]
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: {"available": False, "clients": []})

    response = client.get("/api/v1/clients")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert [item["display_label"] for item in body["clients"]] == ["Client 01", "Client 02", "Client 03"]
    assert {item["client_id"] for item in body["clients"]} == {item.client_id for item in registered}


def test_five_client_listing_returns_all_registered_clients(monkeypatch):
    lab_accounting_service.registry.reset()
    lab_accounting_service.registry.register()
    lab_accounting_service.registry.register()
    lab_accounting_service.registry.register()
    lab_accounting_service.registry.register()
    lab_accounting_service.registry.register()
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: {"available": False, "clients": []})

    response = client.get("/api/v1/clients")

    assert response.status_code == 200
    assert response.json()["count"] == 5
    assert len(response.json()["clients"]) == 5


def test_empty_registry_returns_empty_list_not_fabricated_client(monkeypatch):
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: {"available": False, "clients": []})

    body = client.get("/api/v1/clients").json()

    assert body["count"] == 0
    assert body["clients"] == []
    assert body["available"] is False


def test_existing_detail_returns_only_requested_client(monkeypatch):
    first = lab_accounting_service.registry.register()
    second = lab_accounting_service.registry.register()
    observations = {
        first.client_id: _observation(first.client_id, download=11.0),
        second.client_id: _observation(second.client_id, download=22.0),
    }
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: _available_result(observations))

    response = client.get(f"/api/v1/clients/{first.client_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["client_id"] == first.client_id
    assert body["display_label"] == "Client 01"
    assert body["latest_observation"]["metadata"]["client_id"] == first.client_id
    assert body["latest_observation"]["download_mbps"] == 11.0
    assert second.client_id not in response.text
    assert "22.0" not in response.text


def test_unknown_valid_id_returns_404():
    response = client.get("/api/v1/clients/client-0123456789abcdef")
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown_client"


def test_malformed_id_returns_422():
    assert client.get("/api/v1/clients/not-an-id").status_code == 422


def test_each_client_receives_only_its_own_latest_observation(monkeypatch):
    clients = [lab_accounting_service.registry.register() for _ in range(3)]
    observations = {
        item.client_id: _observation(item.client_id, download=float(index))
        for index, item in enumerate(clients, start=1)
    }
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: _available_result(observations))

    body = client.get("/api/v1/clients").json()

    for index, item in enumerate(body["clients"], start=1):
        assert item["latest_observation"]["metadata"]["client_id"] == item["client_id"]
        assert item["latest_observation"]["download_mbps"] == float(index)


def test_client_two_observation_does_not_leak_to_client_one(monkeypatch):
    first = lab_accounting_service.registry.register()
    second = lab_accounting_service.registry.register()
    monkeypatch.setattr(
        lab_accounting_service,
        "collect",
        lambda: _available_result({second.client_id: _observation(second.client_id, download=42.0)}),
    )

    response = client.get(f"/api/v1/clients/{first.client_id}")

    assert response.status_code == 200
    assert response.json()["latest_observation"] is None
    assert "42.0" not in response.text
    assert second.client_id not in response.text


def test_offline_client_status_is_preserved(monkeypatch):
    registered = lab_accounting_service.registry.register()
    now = datetime.now(timezone.utc)
    lab_accounting_service.registry.observe(_observation_model(registered.client_id, now), now=now)
    lab_accounting_service.registry.mark_offline(registered.client_id, now=now)
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: {"available": False, "clients": []})

    body = client.get("/api/v1/clients").json()
    assert body["clients"][0]["status"] == "offline"


def test_stale_client_status_is_preserved(monkeypatch):
    registered = lab_accounting_service.registry.register()
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    lab_accounting_service.registry.observe(_observation_model(registered.client_id, old), now=old)
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: {"available": False, "clients": []})

    body = client.get("/api/v1/clients").json()
    assert body["clients"][0]["status"] == "offline"
    assert body["clients"][0]["stale"] is True


def _observation_model(client_id, observed_at):
    return TelemetryObservation.model_validate(_observation(client_id, observed_at=observed_at))


def test_missing_observation_is_null(monkeypatch):
    registered = lab_accounting_service.registry.register()
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: _available_result({}))

    body = client.get(f"/api/v1/clients/{registered.client_id}").json()
    assert body["available"] is True
    assert body["latest_observation"] is None


def test_unavailable_collection_is_distinct_from_empty_registry(monkeypatch):
    registered = lab_accounting_service.registry.register()
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: {"available": False, "clients": []})

    body = client.get("/api/v1/clients").json()
    assert body["count"] == 1
    assert body["available"] is False
    assert body["clients"][0]["latest_observation"] is None
    assert body["message"]
    assert registered.client_id in client.get("/api/v1/clients").text


def test_collection_exception_is_safe_and_logged(monkeypatch, caplog):
    def fail():
        raise RuntimeError("secret interface 192.0.2.10 must not leak")

    monkeypatch.setattr(lab_accounting_service, "collect", fail)
    with caplog.at_level("WARNING"):
        response = client.get("/api/v1/clients")

    assert response.status_code == 200
    assert "secret interface" not in response.text
    assert "192.0.2.10" not in response.text
    assert "anonymous client telemetry unavailable" in caplog.text


def test_responses_contain_no_private_identity_or_infrastructure_names(monkeypatch):
    registered = lab_accounting_service.registry.register()
    observation = _observation(registered.client_id)
    monkeypatch.setattr(
        lab_accounting_service,
        "collect",
        lambda: {
            **_available_result({registered.client_id: observation}),
            "internal": "veth-c1-br / namespace client1 / 192.0.2.2 / aa:bb:cc:dd:ee:ff",
        },
    )

    response = client.get("/api/v1/clients")
    serialized = response.text.lower()

    assert response.status_code == 200
    for forbidden in ("192.0.2.2", "aa:bb:cc:dd:ee:ff", "client1", "veth-c1-br"):
        assert forbidden not in serialized
    error = response.json()["clients"][0]["latest_observation"].get("metadata", {}).get("collector_error") or ""
    assert "namespace" not in error
    assert "internal" not in serialized

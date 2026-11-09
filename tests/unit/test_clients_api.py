from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.lab_accounting_service import lab_accounting_service


client = TestClient(app)


def test_client_listing_is_anonymous_and_does_not_expose_lab_details(monkeypatch):
    monkeypatch.setattr(
        lab_accounting_service,
        "collect",
        lambda: {"available": False, "clients": []},
    )
    lab_accounting_service.registry.reset()
    registered = lab_accounting_service.registry.register()

    response = client.get("/api/v1/clients")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["clients"][0]["client_id"] == registered.client_id
    serialized = response.text.lower()
    assert "ip" not in serialized
    assert "mac" not in serialized
    assert "client1" not in serialized
    assert "veth-c" not in serialized


def test_client_detail_and_validation(monkeypatch):
    lab_accounting_service.registry.reset()
    registered = lab_accounting_service.registry.register()
    monkeypatch.setattr(
        lab_accounting_service,
        "collect",
        lambda: {"available": False, "clients": []},
    )

    response = client.get(f"/api/v1/clients/{registered.client_id}")
    assert response.status_code == 200
    assert response.json()["display_label"] == "Client 01"

    assert client.get("/api/v1/clients/not-an-id").status_code == 422
    assert client.get("/api/v1/clients/client-0123456789abcdef").status_code == 404

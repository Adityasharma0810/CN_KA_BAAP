from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.lab_accounting_service import lab_accounting_service


client = TestClient(app)


def test_topology_reports_aggregate_hotspot_when_lab_unavailable(monkeypatch):
    monkeypatch.setattr(lab_accounting_service, "collect", lambda: {"available": False, "clients": []})

    status = client.get("/api/v1/gateway/status")
    topology = client.get("/api/v1/network/topology")

    assert status.status_code == 200
    assert status.json()["status"] == "unavailable"
    assert status.json()["client_count"] == 0
    assert topology.status_code == 200
    body = topology.json()
    assert body["physical_hotspot_aggregate"] is True
    assert [node["label"] for node in body["nodes"]] == [
        "Experience Budget host", "Physical hotspot aggregate"
    ]
    assert "veth" not in topology.text.lower()
    assert "client1" not in topology.text.lower()


def test_topology_lists_measured_anonymous_lab_clients(monkeypatch):
    monkeypatch.setattr(
        lab_accounting_service,
        "collect",
        lambda: {
            "available": True,
            "clients": [
                {
                    "client_id": "client-0123456789abcdef",
                    "observation": {
                        "metadata": {
                            "quality": "measured",
                            "observed_at": "2026-11-09T12:00:00Z",
                        }
                    },
                },
                {
                    "client_id": "client-fedcba9876543210",
                    "observation": {
                        "metadata": {
                            "quality": "unavailable",
                            "observed_at": "2026-11-09T12:00:00Z",
                        }
                    },
                },
            ],
        },
    )

    response = client.get("/api/v1/network/topology")

    assert response.status_code == 200
    body = response.json()
    assert body["physical_hotspot_aggregate"] is False
    assert [node["label"] for node in body["nodes"]] == [
        "Experience Budget host", "Simulated Linux gateway", "Client 01", "Client 02"
    ]
    assert body["nodes"][2]["client_id"] == "client-0123456789abcdef"
    assert body["nodes"][3]["status"] == "unavailable"
    assert "veth" not in response.text.lower()

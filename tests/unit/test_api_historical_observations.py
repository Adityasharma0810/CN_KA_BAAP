from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.schemas import TelemetryObservation
from network.telemetry.metrics_store import MetricsStore


client = TestClient(app)
CLIENT_ONE = "client-aaaaaaaaaaaaaaaa"
CLIENT_TWO = "client-bbbbbbbbbbbbbbbb"
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _observation(source, scope, observed_at, *, environment="physical_host", client_id=None, download=1.0, quality="measured", stale=False):
    metadata = {
        "observed_at": observed_at,
        "source": source,
        "scope": scope,
        "quality": quality,
        "environment": environment,
        "stale": stale,
    }
    if client_id is not None:
        metadata["client_id"] = client_id
    return TelemetryObservation(metadata=metadata, download_mbps=download)


def _seed(path):
    store = MetricsStore(path)
    store.register_client(CLIENT_ONE, "Client 01", environment="simulated_lab", simulated_lab_slot=1)
    store.register_client(CLIENT_TWO, "Client 02", environment="simulated_lab", simulated_lab_slot=2)
    store.save_observations([
        _observation("windows_host", "aggregate_gateway", T0, download=10),
        _observation("windows_hotspot", "aggregate_hotspot", T0 + timedelta(seconds=1), download=20),
        _observation("linux_namespace_lab", "client", T0 + timedelta(seconds=2), environment="simulated_lab", client_id=CLIENT_ONE, download=1),
        _observation("linux_namespace_lab", "client", T0 + timedelta(seconds=3), environment="simulated_lab", client_id=CLIENT_TWO, download=2),
        _observation("linux_namespace_lab", "client", T0 + timedelta(seconds=4), environment="simulated_lab", client_id=CLIENT_ONE, download=3, stale=True),
    ])
    return store


def test_history_defaults_to_aggregate_rows_and_reports_total(monkeypatch, tmp_path):
    path = tmp_path / "history.sqlite3"
    _seed(path)
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))

    response = client.get("/api/v1/observations/history?order=oldest")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["count"] == 2
    assert body["has_more"] is False
    assert {item["observation"]["metadata"]["scope"] for item in body["observations"]} == {"aggregate_gateway", "aggregate_hotspot"}
    assert body["filters"]["order"] == "oldest"


def test_history_filters_are_inclusive_and_paginated(monkeypatch, tmp_path):
    path = tmp_path / "history.sqlite3"
    _seed(path)
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))

    response = client.get(
        "/api/v1/observations/history"
        "?source=windows_host&start=2026-11-09T12:00:00Z"
        "&end=2026-11-09T12:00:00Z&limit=1&offset=0"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["count"] == 1
    assert body["has_more"] is False
    assert body["observations"][0]["observation"]["download_mbps"] == 10.0


def test_client_history_isolated_and_preserves_stored_values(monkeypatch, tmp_path):
    path = tmp_path / "history.sqlite3"
    _seed(path)
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))

    response = client.get(f"/api/v1/clients/{CLIENT_ONE}/history?order=oldest")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert [item["observation"]["download_mbps"] for item in body["observations"]] == [1.0, 3.0]
    assert all(item["observation"]["metadata"]["client_id"] == CLIENT_ONE for item in body["observations"])
    assert CLIENT_TWO not in response.text
    assert body["observations"][1]["observation"]["metadata"]["stale"] is True


def test_client_history_unknown_and_malformed_ids(monkeypatch, tmp_path):
    path = tmp_path / "history.sqlite3"
    _seed(path)
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))

    assert client.get("/api/v1/clients/client-cccccccccccccccc/history").json() == {"detail": "unknown_client"}
    assert client.get("/api/v1/clients/not-an-id/history").status_code == 422


def test_history_rejects_bad_ranges_and_injection_like_values(monkeypatch, tmp_path):
    path = tmp_path / "history.sqlite3"
    _seed(path)
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))

    reversed_range = client.get(
        "/api/v1/observations/history?start=2026-11-10T00:00:00Z&end=2026-11-09T00:00:00Z"
    )
    invalid_source = client.get("/api/v1/observations/history?source=windows_host%27%20OR%201%3D1")
    invalid_limit = client.get("/api/v1/observations/history?limit=1001")

    assert reversed_range.status_code == 422
    assert reversed_range.json() == {"detail": "invalid_time_range"}
    assert invalid_source.status_code == 422
    assert invalid_limit.status_code == 422
    assert "SELECT" not in reversed_range.text.upper()
    assert str(tmp_path) not in reversed_range.text


def test_history_missing_database_is_empty_without_collection(monkeypatch, tmp_path):
    path = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))

    response = client.get("/api/v1/observations/history")

    assert response.status_code == 200
    assert response.json()["total_count"] == 0
    assert response.json()["observations"] == []
    assert not path.exists()

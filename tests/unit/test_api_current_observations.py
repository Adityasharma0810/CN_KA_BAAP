"""Contract, separation, and privacy tests for current observations."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.schemas import TelemetryObservation
from network.telemetry.metrics_store import MetricsStore


client = TestClient(app)

CLIENT_ONE = "client-aaaaaaaaaaaaaaaa"
CLIENT_TWO = "client-bbbbbbbbbbbbbbbb"


def _database(tmp_path, name="current.sqlite3"):
    path = tmp_path / name
    MetricsStore(path)
    return path


def _use_database(monkeypatch, path) -> None:
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))


def _observation(
    source: str,
    scope: str,
    *,
    observed_at: datetime | None = None,
    environment: str = "physical_host",
    quality: str = "measured",
    client_id: str | None = None,
    download_mbps: float | None = 1.0,
    upload_mbps: float | None = 0.5,
) -> TelemetryObservation:
    metadata = {
        "observed_at": observed_at or datetime.now(timezone.utc),
        "source": source,
        "scope": scope,
        "quality": quality,
        "environment": environment,
    }
    if client_id is not None:
        metadata["client_id"] = client_id
    return TelemetryObservation(
        metadata=metadata,
        download_mbps=download_mbps,
        upload_mbps=upload_mbps,
    )


def _register_clients(store: MetricsStore) -> None:
    store.register_client(
        CLIENT_ONE,
        "Client 01",
        environment="simulated_lab",
        simulated_lab_slot=1,
    )
    store.register_client(
        CLIENT_TWO,
        "Client 02",
        environment="simulated_lab",
        simulated_lab_slot=2,
    )


def _seed_aggregate(store: MetricsStore, now: datetime) -> None:
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            observed_at=now - timedelta(seconds=30),
        )
    )
    store.save_observation(
        _observation(
            "windows_hotspot",
            "aggregate_hotspot",
            observed_at=now - timedelta(seconds=20),
        )
    )
    store.save_observation(
        _observation(
            "linux_gateway",
            "aggregate_gateway",
            observed_at=now - timedelta(seconds=10),
            environment="simulated_lab",
        )
    )


def test_current_defaults_to_aggregate_sources_only(monkeypatch, tmp_path):
    path = _database(tmp_path)
    store = MetricsStore(path)
    now = datetime.now(timezone.utc)
    _seed_aggregate(store, now)
    _register_clients(store)
    store.save_observation(
        _observation(
            "linux_namespace_lab",
            "client",
            observed_at=now,
            environment="simulated_lab",
            client_id=CLIENT_ONE,
        )
    )
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/observations/current")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    sources = [item["observation"]["metadata"]["source"] for item in body["observations"]]
    assert sources == ["linux_gateway", "windows_hotspot", "windows_host"]
    assert all(
        item["observation"]["metadata"]["scope"] != "client"
        for item in body["observations"]
    )
    assert body["filters"] == {
        "source": None,
        "scope": None,
        "environment": None,
        "client_id": None,
    }


def test_current_source_filter_returns_only_that_source(monkeypatch, tmp_path):
    path = _database(tmp_path)
    store = MetricsStore(path)
    _seed_aggregate(store, datetime.now(timezone.utc))
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?source=windows_host"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["filters"]["source"] == "windows_host"
    assert body["observations"][0]["observation"]["metadata"]["source"] == (
        "windows_host"
    )


def test_current_returns_newest_per_source(monkeypatch, tmp_path):
    path = _database(tmp_path)
    store = MetricsStore(path)
    now = datetime.now(timezone.utc)
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            observed_at=now - timedelta(minutes=1),
            download_mbps=1.0,
        )
    )
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            observed_at=now,
            download_mbps=2.0,
        )
    )
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?source=windows_host"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["observations"][0]["observation"]["download_mbps"] == 2.0


def test_current_client_scope_returns_one_row_per_client(monkeypatch, tmp_path):
    path = _database(tmp_path)
    store = MetricsStore(path)
    now = datetime.now(timezone.utc)
    _register_clients(store)
    store.save_observation(
        _observation(
            "linux_namespace_lab",
            "client",
            observed_at=now - timedelta(seconds=5),
            environment="simulated_lab",
            client_id=CLIENT_ONE,
        )
    )
    store.save_observation(
        _observation(
            "linux_namespace_lab",
            "client",
            observed_at=now,
            environment="simulated_lab",
            client_id=CLIENT_TWO,
        )
    )
    _seed_aggregate(store, now)
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?scope=client"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert {
        item["observation"]["metadata"]["client_id"]
        for item in body["observations"]
    } == {CLIENT_ONE, CLIENT_TWO}
    assert all(
        item["observation"]["metadata"]["scope"] == "client"
        for item in body["observations"]
    )


def test_current_client_id_returns_only_that_client(monkeypatch, tmp_path):
    path = _database(tmp_path)
    store = MetricsStore(path)
    now = datetime.now(timezone.utc)
    _register_clients(store)
    store.save_observation(
        _observation(
            "linux_namespace_lab",
            "client",
            observed_at=now,
            environment="simulated_lab",
            client_id=CLIENT_ONE,
            download_mbps=3.0,
        )
    )
    store.save_observation(
        _observation(
            "linux_namespace_lab",
            "client",
            observed_at=now,
            environment="simulated_lab",
            client_id=CLIENT_TWO,
            download_mbps=7.0,
        )
    )
    _use_database(monkeypatch, path)

    response = client.get(
        f"/api/v1/observations/current?client_id={CLIENT_ONE}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["observations"][0]["observation"]["metadata"]["client_id"] == (
        CLIENT_ONE
    )
    assert body["observations"][0]["observation"]["download_mbps"] == 3.0


def test_current_unknown_client_returns_404(monkeypatch, tmp_path):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?client_id=client-cccccccccccccccc"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "unknown_client"}


def test_current_malformed_client_returns_422(monkeypatch, tmp_path):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?client_id=not-a-client"
    )

    assert response.status_code == 422


def test_current_invalid_source_returns_422(monkeypatch, tmp_path):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?source=made_up"
    )

    assert response.status_code == 422


def test_current_rejects_conflicting_client_and_aggregate_scope(
    monkeypatch, tmp_path
):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    response = client.get(
        f"/api/v1/observations/current?client_id={CLIENT_ONE}"
        "&scope=aggregate_gateway"
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_filter"}


def test_current_empty_database_returns_empty_collection(monkeypatch, tmp_path):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/observations/current")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["observations"] == []


def test_current_missing_database_returns_empty_without_creating_it(
    monkeypatch, tmp_path
):
    path = tmp_path / "missing.sqlite3"
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/observations/current")

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert not path.exists()


def test_current_marks_old_observation_stale(monkeypatch, tmp_path):
    path = _database(tmp_path)
    store = MetricsStore(path)
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            observed_at=old,
        )
    )
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?source=windows_host"
    )

    assert response.status_code == 200
    metadata = response.json()["observations"][0]["observation"]["metadata"]
    assert metadata["stale"] is True


def test_current_preserves_unavailable_values_as_null(monkeypatch, tmp_path):
    path = _database(tmp_path)
    store = MetricsStore(path)
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            download_mbps=None,
            upload_mbps=None,
            quality="unavailable",
        )
    )
    _use_database(monkeypatch, path)

    response = client.get(
        "/api/v1/observations/current?source=windows_host"
    )

    observation = response.json()["observations"][0]["observation"]
    assert observation["download_mbps"] is None
    assert observation["upload_mbps"] is None
    assert observation["metadata"]["quality"] == "unavailable"


def test_current_corrupt_database_returns_safe_503(monkeypatch, tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"not a sqlite database")
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/observations/current")

    assert response.status_code == 503
    assert response.json() == {"detail": "database_unavailable"}
    assert "not a sqlite database" not in response.text
    assert str(tmp_path) not in response.text


def test_current_response_has_no_private_infrastructure_fields(
    monkeypatch, tmp_path
):
    path = _database(tmp_path)
    store = MetricsStore(path)
    _seed_aggregate(store, datetime.now(timezone.utc))
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/observations/current")

    forbidden_keys = {
        "adapter",
        "address",
        "credential",
        "device_name",
        "endpoint",
        "hostname",
        "interface",
        "ip",
        "ip_address",
        "mac",
        "mac_address",
        "namespace",
        "password",
        "path",
        "payload",
        "secret",
        "token",
        "traceback",
        "url",
    }

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key.lower() not in forbidden_keys
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            assert re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", value) is None
            assert re.search(
                r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", value
            ) is None

    walk(response.json())
    assert "Traceback" not in response.text
    assert str(tmp_path) not in response.text

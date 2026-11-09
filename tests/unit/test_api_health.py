"""Contract and privacy tests for the versioned health routes."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import backend.app.services.health_service as health_service
from backend.app.main import app
from backend.app.models.schemas import TelemetryObservation
from backend.app.services.lab_ingest_service import lab_ingest_service
from network.telemetry.metrics_store import MetricsStore


client = TestClient(app)


def _database(tmp_path, name="health.sqlite3"):
    path = tmp_path / name
    MetricsStore(path)
    return path


def _observation(
    source: str,
    scope: str,
    *,
    observed_at: datetime | None = None,
    quality: str = "measured",
) -> TelemetryObservation:
    return TelemetryObservation(
        metadata={
            "observed_at": observed_at or datetime.now(timezone.utc),
            "source": source,
            "scope": scope,
            "quality": quality,
            "environment": "physical_host",
        },
        download_mbps=1.25,
        upload_mbps=0.25,
    )


def _use_database(monkeypatch, path) -> None:
    monkeypatch.setenv("EB_DATABASE_PATH", str(path))


def _use_platform(monkeypatch, name: str) -> None:
    monkeypatch.setattr(health_service.platform, "system", lambda: name)


def test_health_reports_application_database_and_registry(monkeypatch, tmp_path):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)
    _use_platform(monkeypatch, "Linux")
    monkeypatch.setattr(lab_ingest_service, "enabled", False)
    monkeypatch.setattr(lab_ingest_service, "last_error_code", "lab_not_available")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["application"]["status"] == "healthy"
    assert body["components"]["database"]["status"] == "healthy"
    assert body["components"]["database"]["schema_version"] == 1
    assert body["components"]["client_registry"]["status"] == "healthy"
    assert body["components"]["client_registry"]["client_count"] >= 1
    assert body["components"]["gateway"]["status"] == "unavailable"
    assert body["components"]["gateway"]["error_code"] == "lab_not_available"
    assert (
        body["components"]["windows_host_collector"]["error_code"]
        == "not_supported_on_platform"
    )
    assert (
        body["components"]["windows_hotspot_collector"]["error_code"]
        == "not_supported_on_platform"
    )


def test_health_reports_missing_database_without_creating_it(monkeypatch, tmp_path):
    path = tmp_path / "missing.sqlite3"
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"]["status"] == "degraded"
    assert (
        body["components"]["database"]["error_code"]
        == "database_not_initialized"
    )
    assert body["components"]["windows_host_collector"]["status"] == "unavailable"
    assert not path.exists()


def test_health_reports_corrupt_database_as_unavailable(monkeypatch, tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"this is not a sqlite database")
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["components"]["database"]["status"] == "unavailable"
    assert body["components"]["database"]["error_code"] == "database_corrupt"
    assert "not a sqlite database" not in response.text
    assert str(tmp_path) not in response.text


def test_health_reports_newer_database_schema_as_unavailable(
    monkeypatch, tmp_path
):
    path = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA user_version = 999")
        connection.commit()
    finally:
        connection.close()
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["components"]["database"]["status"] == "unavailable"
    assert (
        body["components"]["database"]["error_code"]
        == "database_schema_unsupported"
    )


def test_health_reports_unopenable_database_as_unavailable(monkeypatch, tmp_path):
    path = tmp_path / "directory.sqlite3"
    path.mkdir()
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["components"]["database"]["status"] == "unavailable"
    assert body["components"]["database"]["error_code"] == "database_unavailable"


def test_collectors_endpoint_lists_each_collector(monkeypatch, tmp_path):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health/collectors")

    assert response.status_code == 200
    body = response.json()
    assert [item["collector"] for item in body["collectors"]] == [
        "windows_host",
        "windows_hotspot",
        "linux_gateway",
    ]
    assert all(item["status"] == "unavailable" for item in body["collectors"])
    assert all(item["stale"] is False for item in body["collectors"])


def test_health_reports_fresh_windows_observations(monkeypatch, tmp_path):
    _use_platform(monkeypatch, "Windows")
    path = _database(tmp_path)
    store = MetricsStore(path)
    now = datetime.now(timezone.utc)
    store.save_observation(
        _observation("windows_host", "aggregate_gateway", observed_at=now)
    )
    store.save_observation(
        _observation("windows_hotspot", "aggregate_hotspot", observed_at=now)
    )
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["components"]["windows_host_collector"]["status"] == "healthy"
    assert body["components"]["windows_hotspot_collector"]["status"] == "healthy"
    assert body["components"]["windows_host_collector"]["last_success_at"] is not None
    assert body["components"]["gateway"]["status"] == "unavailable"
    assert body["status"] == "degraded"


def test_health_marks_stale_observations(monkeypatch, tmp_path):
    _use_platform(monkeypatch, "Windows")
    path = _database(tmp_path)
    store = MetricsStore(path)
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    store.save_observation(
        _observation("windows_host", "aggregate_gateway", observed_at=old)
    )
    _use_database(monkeypatch, path)

    health_response = client.get("/api/v1/health")
    collectors_response = client.get("/api/v1/health/collectors")

    assert health_response.status_code == 200
    host = health_response.json()["components"]["windows_host_collector"]
    assert host["status"] == "degraded"
    assert host["error_code"] == "stale_observation"

    collectors = collectors_response.json()["collectors"]
    host_entry = next(
        item for item in collectors if item["collector"] == "windows_host"
    )
    assert host_entry["stale"] is True
    assert host_entry["error_code"] == "stale_observation"


def test_health_marks_unknown_quality_as_degraded(monkeypatch, tmp_path):
    _use_platform(monkeypatch, "Windows")
    path = _database(tmp_path)
    store = MetricsStore(path)
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            quality="unknown",
        )
    )
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")

    host = response.json()["components"]["windows_host_collector"]
    assert host["status"] == "degraded"
    assert host["error_code"] == "quality_unknown"


def test_health_marks_unavailable_quality_as_degraded(monkeypatch, tmp_path):
    _use_platform(monkeypatch, "Windows")
    path = _database(tmp_path)
    store = MetricsStore(path)
    store.save_observation(
        _observation(
            "windows_host",
            "aggregate_gateway",
            quality="unavailable",
        )
    )
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")

    host = response.json()["components"]["windows_host_collector"]
    assert host["status"] == "degraded"
    assert host["error_code"] == "collector_reported_unavailable"
    assert host["last_success_at"] is None


def test_health_reports_registry_failure_safely(monkeypatch, tmp_path):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    def fail():
        raise RuntimeError("registry internals must not leak")

    monkeypatch.setattr(
        health_service.lab_accounting_service.registry,
        "list_clients",
        fail,
    )

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    registry = response.json()["components"]["client_registry"]
    assert registry["status"] == "unavailable"
    assert registry["error_code"] == "registry_unavailable"
    assert "internals" not in response.text
    assert response.json()["status"] == "degraded"


def test_health_does_not_expose_private_infrastructure_fields(
    monkeypatch, tmp_path
):
    path = _database(tmp_path)
    _use_database(monkeypatch, path)

    response = client.get("/api/v1/health")
    body = response.json()

    forbidden_keys = {
        "adapter",
        "address",
        "credential",
        "database_path",
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

    walk(body)
    assert "Traceback" not in response.text
    assert str(tmp_path) not in response.text


def test_product_app_does_not_mount_gateway_control_routes():
    for path in (
        "/policy",
        "/clients",
        "/clients/1/limit",
        "/clients/1/intent",
    ):
        assert client.get(path).status_code == 404
        assert client.post(path, json={}).status_code == 404


def test_openapi_documents_typed_health_responses():
    schema = client.get("/openapi.json").json()

    health_schema = schema["paths"]["/api/v1/health"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    collectors_schema = schema["paths"]["/api/v1/health/collectors"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

    assert health_schema == {"$ref": "#/components/schemas/HealthResponse"}
    assert collectors_schema == {
        "$ref": "#/components/schemas/CollectorsResponse"
    }
    assert "HealthResponse" in schema["components"]["schemas"]
    assert "CollectorsResponse" in schema["components"]["schemas"]


def test_legacy_health_and_root_contract_unchanged():
    health_response = client.get("/health")
    root_response = client.get("/")

    assert health_response.status_code == 200
    assert health_response.json() == {
        "status": "healthy",
        "service": "experience-budget",
    }
    assert root_response.status_code == 200
    assert root_response.json()["mode"] == "baseline_monitoring"

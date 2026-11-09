from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from backend.app.main import app
from backend.app.models.system_schemas import SystemCapabilitiesResponse
from backend.app.services.lab_ingest_service import lab_ingest_service


client = TestClient(app)


def test_system_capabilities_endpoint_is_typed_and_privacy_safe(monkeypatch):
    monkeypatch.setattr(lab_ingest_service, "platform", "linux")
    monkeypatch.setattr(lab_ingest_service, "enabled", True)
    monkeypatch.setattr(lab_ingest_service, "last_error_code", None)
    monkeypatch.setattr(
        lab_ingest_service,
        "last_success_at",
        datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    )

    response = client.get("/api/v1/system/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "linux"
    assert body["windows_collectors_supported"] is False
    assert body["lab_ingest_enabled"] is True
    assert body["lab_ingest_last_success"] == "2026-11-09T12:00:00Z"
    assert "path" not in response.text.lower()
    assert "hostname" not in response.text.lower()


def test_system_capabilities_schema_forbids_extra_fields():
    with pytest.raises(ValidationError):
        SystemCapabilitiesResponse(
            platform="linux",
            windows_collectors_supported=False,
            lab_ingest_enabled=False,
            lab_ingest_state="disabled",
            lab_ingest_interval_seconds=2,
            lab_ingest_last_success=None,
            lab_ingest_last_error_code=None,
            observation_freshness_threshold_seconds=300,
            private_path="/tmp/private",
        )


def test_openapi_documents_system_capabilities():
    schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/api/v1/system/capabilities"]["get"]
    response_schema = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert response_schema == {
        "$ref": "#/components/schemas/SystemCapabilitiesResponse"
    }

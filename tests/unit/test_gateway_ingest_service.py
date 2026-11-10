import asyncio
from datetime import datetime, timezone
from pathlib import Path

from backend.app.services.gateway_ingest_service import GatewayIngestService
from backend.app.services.gateway_transport_service import GatewayObservationResponse
from network.telemetry.metrics_store import MetricsStore


NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def response():
    return GatewayObservationResponse.model_validate(
        {
            "version": 1,
            "observed_at": NOW.isoformat(),
            "observations": [
                {
                    "metadata": {
                        "observed_at": NOW.isoformat(),
                        "source": "linux_namespace_lab",
                        "scope": "client",
                        "quality": "measured",
                        "environment": "simulated_lab",
                        "client_id": "client-abcdefgh",
                    },
                    "download_mbps": 12.5,
                    "upload_mbps": 1.2,
                }
            ],
        }
    )


class FakeTransport:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def fetch_current(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_collect_once_persists_validated_gateway_observations(tmp_path: Path):
    transport = FakeTransport(result=response())
    service = GatewayIngestService(
        transport=transport,
        db_path_provider=lambda: tmp_path / "gateway.sqlite3",
        clock=lambda: NOW,
    )

    result = asyncio.run(service.collect_once())

    assert result.error_code is None
    assert service.state == "connected"
    assert service.last_success_at == NOW
    stored = MetricsStore(tmp_path / "gateway.sqlite3").get_history_by_source(
        "linux_namespace_lab", scope="client", order="oldest"
    )
    assert len(stored) == 1
    assert transport.calls == 1


def test_transport_failure_reports_disconnected_without_private_error(tmp_path: Path):
    from backend.app.services.gateway_transport_service import GatewayTransportError

    service = GatewayIngestService(
        transport=FakeTransport(error=GatewayTransportError("gateway_timeout")),
        db_path_provider=lambda: tmp_path / "gateway.sqlite3",
        clock=lambda: NOW,
    )

    result = asyncio.run(service.collect_once())

    assert result.error_code == "gateway_timeout"
    assert service.state == "disconnected"
    assert service.last_success_at is None

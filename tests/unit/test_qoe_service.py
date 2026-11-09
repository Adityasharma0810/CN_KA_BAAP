from datetime import datetime, timezone
from types import SimpleNamespace

import backend.app.services.qoe_service as qoe_module
from backend.app.models.schemas import TelemetryObservation


NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
CLIENT_ID = "client-12345678"


def observation(*, scope, source, client_id=None, **values):
    return TelemetryObservation(
        metadata={
            "observed_at": NOW,
            "source": source,
            "scope": scope,
            "quality": "measured",
            "environment": "simulated_lab",
            "client_id": client_id,
        },
        **values,
    )


def test_current_qoe_uses_declared_class_and_same_cycle_capacity(monkeypatch):
    client = observation(
        scope="client",
        source="linux_namespace_lab",
        client_id=CLIENT_ID,
        rtt_ms=0,
        rtt_variation_ms=0,
        packet_loss_percent=0,
        download_mbps=0,
    )
    aggregate = observation(
        scope="aggregate_gateway",
        source="linux_gateway",
        download_mbps=12,
    )
    monkeypatch.setattr(
        qoe_module,
        "scenario_service",
        SimpleNamespace(
            active_profiles={1: "call"},
            active_started_at=NOW,
        ),
    )
    monkeypatch.setattr(
        qoe_module,
        "lab_accounting_service",
        SimpleNamespace(
            inventory=(SimpleNamespace(client_id=CLIENT_ID, client_number=1),)
        ),
    )
    monkeypatch.setattr(
        qoe_module,
        "build_current_observations",
        lambda **_kwargs: SimpleNamespace(
            observations=[SimpleNamespace(observation=client)]
        ),
    )

    def historical(*, source, **_kwargs):
        samples = [client] * 5 if source == "linux_namespace_lab" else [aggregate]
        return SimpleNamespace(
            observations=[SimpleNamespace(observation=item) for item in samples]
        )

    monkeypatch.setattr(qoe_module, "build_historical_observations", historical)

    response = qoe_module.build_current_qoe(requested_at=NOW)

    assert response.clients[0].traffic_class == "call"
    assert response.clients[0].class_source == "scenario_declared"
    assert response.clients[0].score == 100
    assert response.clients[0].band == "green"
    assert response.clients[0].inputs["rtt_ms"].unit == "ms"
    assert response.clients[0].inputs["rtt_ms"].observed_at == NOW

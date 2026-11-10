from datetime import datetime, timezone

import pytest

from backend.app.models.schemas import TelemetryObservation
from backend.app.services.gateway_transport_service import (
    GatewayAuthenticationError,
    GatewaySchemaError,
    GatewayTransport,
    GatewayTransportError,
)


NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def observation():
    return TelemetryObservation(
        metadata={
            "observed_at": NOW,
            "source": "linux_namespace_lab",
            "scope": "client",
            "quality": "measured",
            "environment": "simulated_lab",
            "client_id": "client-abcdefgh",
        },
        download_mbps=12.5,
        upload_mbps=1.2,
    ).model_dump(mode="json")


def response_payload():
    return {
        "version": 1,
        "observed_at": NOW.isoformat(),
        "observations": [observation()],
    }


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def close(self):
        pass


def transport(fake_client, *, token="secret-token"):
    return GatewayTransport(
        "http://gateway.example:8100",
        token=token,
        client_factory=lambda **_: fake_client,
        max_attempts=1,
    )


def test_fetch_validates_version_and_sends_bearer_authentication():
    client = FakeClient(FakeResponse(payload=response_payload()))
    result = transport(client).fetch_current()

    assert result.version == 1
    assert result.observations[0].metadata.client_id == "client-abcdefgh"
    assert client.calls[0][0] == "http://gateway.example:8100/api/v1/observations/current"
    assert client.calls[0][1]["headers"]["Authorization"] == "Bearer secret-token"
    assert client.calls[0][1]["timeout"] == 2.0


def test_transport_does_not_send_an_authorization_header_without_a_token():
    client = FakeClient(FakeResponse(payload=response_payload()))
    transport(client, token=None).fetch_current()

    assert "Authorization" not in client.calls[0][1]["headers"]


def test_authentication_failure_is_not_retried():
    client = FakeClient(FakeResponse(status_code=401, payload={}))
    with pytest.raises(GatewayAuthenticationError):
        transport(client).fetch_current()
    assert len(client.calls) == 1


def test_malformed_payload_is_rejected():
    client = FakeClient(
        FakeResponse(payload={"version": 1, "observations": [{"bad": True}]})
    )
    with pytest.raises(GatewaySchemaError):
        transport(client).fetch_current()


def test_duplicate_client_observations_are_rejected():
    payload = response_payload()
    payload["observations"].append(observation())
    client = FakeClient(FakeResponse(payload=payload))

    with pytest.raises(GatewaySchemaError):
        transport(client).fetch_current()


def test_namespace_observation_cannot_claim_physical_environment():
    payload = response_payload()
    payload["observations"][0]["metadata"]["environment"] = "physical_host"
    client = FakeClient(FakeResponse(payload=payload))

    with pytest.raises(GatewaySchemaError):
        transport(client).fetch_current()


def test_oversized_response_is_rejected_before_json_parsing():
    client = FakeClient(
        FakeResponse(
            payload=response_payload(),
            content=b"x" * (1024 * 1024 + 1),
        )
    )
    with pytest.raises(GatewaySchemaError):
        transport(client).fetch_current()


def test_transport_failure_is_safe_and_bounded():
    class FailingClient(FakeClient):
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            raise TimeoutError("private detail")

    client = FailingClient(None)
    service = GatewayTransport(
        "http://gateway.example:8100",
        client_factory=lambda **_: client,
        max_attempts=2,
    )
    with pytest.raises(GatewayTransportError) as error:
        service.fetch_current()
    assert error.value.code == "gateway_timeout"
    assert len(client.calls) == 2

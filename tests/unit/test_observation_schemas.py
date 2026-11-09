from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationMetadata,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)


def metadata(**overrides):
    values = {
        "observed_at": "2026-11-09T12:00:00+05:30",
        "source": ObservationSource.WINDOWS_HOST,
        "scope": ObservationScope.AGGREGATE_GATEWAY,
        "quality": ValueQuality.MEASURED,
        "environment": ObservationEnvironment.PHYSICAL_HOST,
    }
    values.update(overrides)
    return values


def test_timestamp_is_normalized_to_utc():
    result = ObservationMetadata.model_validate(metadata())

    assert result.observed_at == datetime(2026, 11, 9, 6, 30, tzinfo=timezone.utc)


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValidationError, match="timezone"):
        ObservationMetadata.model_validate(metadata(observed_at="2026-11-09T12:00:00"))


def test_client_observation_requires_opaque_client_id():
    with pytest.raises(ValidationError, match="require an anonymous client_id"):
        TelemetryObservation(
            metadata=metadata(scope=ObservationScope.CLIENT),
            download_bytes=100,
        )

    sample = TelemetryObservation(
        metadata=metadata(
            source=ObservationSource.LINUX_NAMESPACE_LAB,
            scope=ObservationScope.CLIENT,
            environment=ObservationEnvironment.SIMULATED_LAB,
            client_id="client-0123456789abcdef",
        ),
        download_bytes=100,
    )
    assert sample.metadata.client_id == "client-0123456789abcdef"


def test_aggregate_observation_cannot_contain_client_id():
    with pytest.raises(ValidationError, match="only for client observations"):
        ObservationMetadata.model_validate(metadata(client_id="client-0123456789abcdef"))


def test_forbidden_identity_fields_are_rejected():
    with pytest.raises(ValidationError):
        TelemetryObservation(
            metadata=metadata(),
            ip_address="192.0.2.10",
        )

    with pytest.raises(ValidationError, match="forbidden identity"):
        ObservationMetadata.model_validate(
            metadata(collector_error="failed for IP address 192.0.2.10")
        )


def test_error_metadata_rejects_addresses_paths_and_infrastructure():
    for value in (
        "failed at 192.0.2.10",
        "failed at 2001:db8::1",
        "failed for 00:11:22:33:44:55",
        "https://example.invalid/private",
        "C:\\Users\\Alice\\secret.txt",
        "counter interface unavailable: veth-c1-br",
        "client-0123456789abcdef",
        "/home/alice/.ssh/id_ed25519",
    ):
        with pytest.raises(ValidationError, match="forbidden identity"):
            ObservationMetadata.model_validate(metadata(collector_error=value))


def test_safe_error_codes_are_accepted():
    result = ObservationMetadata.model_validate(
        metadata(collector_error="rate_unavailable:no_baseline")
    )

    assert result.collector_error == "rate_unavailable:no_baseline"


def test_unavailable_metrics_remain_none_and_extra_fields_are_forbidden():
    sample = TelemetryObservation(
        metadata=metadata(quality=ValueQuality.UNAVAILABLE),
        download_mbps=None,
        packet_loss_percent=None,
    )

    assert sample.download_mbps is None
    with pytest.raises(ValidationError):
        TelemetryObservation(metadata=metadata(), made_up_metric=0)


def test_invalid_metric_ranges_are_rejected():
    with pytest.raises(ValidationError):
        TelemetryObservation(metadata=metadata(), packet_loss_percent=101)

    with pytest.raises(ValidationError):
        TelemetryObservation(metadata=metadata(), download_bytes=True)

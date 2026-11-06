
import pytest

from network.telemetry.hotspot_bandwidth_monitor import (
    calculate_client_rates,
)


def test_client_download_direction():
    previous = {
        "received_bytes": 1000,
        "sent_bytes": 500,
    }

    current = {
        "received_bytes": 251000,
        "sent_bytes": 100500,
    }

    result = calculate_client_rates(previous, current, 2)

    assert result["client_download_mbps"] == 0.4
    assert result["client_upload_mbps"] == 1.0


def test_zero_elapsed_rejected():
    with pytest.raises(ValueError):
        calculate_client_rates(
            {"received_bytes": 100, "sent_bytes": 100},
            {"received_bytes": 200, "sent_bytes": 200},
            0,
        )


def test_counter_reset_rejected():
    with pytest.raises(ValueError):
        calculate_client_rates(
            {"received_bytes": 1000, "sent_bytes": 1000},
            {"received_bytes": 500, "sent_bytes": 1500},
            1,
        )

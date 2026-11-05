
import pytest

from network.telemetry.bandwidth_monitor import calculate_rates


def test_calculate_bandwidth_rates():
    previous = {
        "received_bytes": 1000,
        "sent_bytes": 500,
    }

    current = {
        "received_bytes": 251000,
        "sent_bytes": 100500,
    }

    result = calculate_rates(previous, current, 2.0)

    assert result["download_mbps"] == 1.0
    assert result["upload_mbps"] == 0.4


def test_reject_zero_elapsed_time():
    with pytest.raises(ValueError):
        calculate_rates(
            {"received_bytes": 100, "sent_bytes": 100},
            {"received_bytes": 200, "sent_bytes": 200},
            0
        )


def test_detect_counter_reset():
    with pytest.raises(ValueError):
        calculate_rates(
            {"received_bytes": 1000, "sent_bytes": 1000},
            {"received_bytes": 500, "sent_bytes": 1500},
            1
        )

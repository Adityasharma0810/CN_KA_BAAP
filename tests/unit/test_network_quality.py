
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from network.telemetry.network_quality import (
    ping_once,
    summarize_rtts,
)


def test_normal_rtt_statistics():
    result = summarize_rtts([10, 12, 14], 3)

    assert result["rtt_min_ms"] == 10
    assert result["rtt_avg_ms"] == 12
    assert result["rtt_max_ms"] == 14
    assert result["rtt_jitter_avg_ms"] == 2
    assert result["packet_loss_percent"] == 0
    assert result["status"] == "healthy"


def test_packet_loss_calculation():
    result = summarize_rtts([10, None, 14, None], 4)

    assert result["probes_received"] == 2
    assert result["packet_loss_percent"] == 50
    assert result["rtt_jitter_avg_ms"] == 4
    assert result["status"] == "packet_loss"


def test_complete_packet_loss():
    result = summarize_rtts([None, None, None], 3)

    assert result["packet_loss_percent"] == 100
    assert result["rtt_avg_ms"] is None
    assert result["rtt_jitter_avg_ms"] is None
    assert result["status"] == "no_icmp_reply"


def test_parse_windows_ping_response():
    response = SimpleNamespace(
        stdout="Reply from 1.1.1.1: bytes=32 time=15ms TTL=57",
        stderr="",
    )

    with patch(
        "network.telemetry.network_quality.subprocess.run",
        return_value=response,
    ):
        assert ping_once("1.1.1.1") == 15


def test_parse_submillisecond_response():
    response = SimpleNamespace(
        stdout="Reply from 1.1.1.1: bytes=32 time<1ms TTL=57",
        stderr="",
    )

    with patch(
        "network.telemetry.network_quality.subprocess.run",
        return_value=response,
    ):
        assert ping_once("1.1.1.1") == 0.5


def test_reject_hostname():
    with pytest.raises(ValueError):
        ping_once("example.com")


def test_reject_zero_probes():
    with pytest.raises(ValueError):
        summarize_rtts([], 0)

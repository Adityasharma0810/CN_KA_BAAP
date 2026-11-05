
import pytest

from network.telemetry.metrics_store import MetricsStore


@pytest.fixture
def store(tmp_path):
    return MetricsStore(
        tmp_path / "test_metrics.sqlite3"
    )


def sample():
    return {
        "interface_label": "Wi-Fi",
        "download_mbps": 12.5,
        "upload_mbps": 2.5,
        "adapter_up": True,
        "internet_reachable": True,
        "probe_target": "1.1.1.1",
        "probes_sent": 10,
        "probes_received": 10,
        "packet_loss_percent": 0,
        "rtt_min_ms": 10,
        "rtt_avg_ms": 15,
        "rtt_max_ms": 20,
        "rtt_jitter_avg_ms": 2.5,
    }


def test_database_initialization(store):
    assert store.count_samples() == 0


def test_insert_and_retrieve_sample(store):
    sample_id = store.insert_sample(sample())

    records = store.get_recent_samples()

    assert sample_id == 1
    assert len(records) == 1
    assert records[0]["download_mbps"] == 12.5
    assert records[0]["upload_mbps"] == 2.5
    assert records[0]["internet_reachable"] == 1


def test_multiple_samples(store):
    first = sample()
    second = sample()

    second["download_mbps"] = 25.0

    store.insert_sample(first)
    store.insert_sample(second)

    records = store.get_recent_samples()

    assert len(records) == 2
    assert records[0]["download_mbps"] == 25.0
    assert records[1]["download_mbps"] == 12.5


def test_reject_unsupported_private_fields(store):
    data = sample()
    data["connected_device_mac"] = "00:11:22:33:44:55"

    with pytest.raises(ValueError):
        store.insert_sample(data)


def test_reject_negative_bandwidth(store):
    data = sample()
    data["download_mbps"] = -10

    with pytest.raises(ValueError):
        store.insert_sample(data)


def test_reject_invalid_packet_loss(store):
    data = sample()
    data["packet_loss_percent"] = 150

    with pytest.raises(ValueError):
        store.insert_sample(data)


def test_reject_invalid_probe_target(store):
    data = sample()
    data["probe_target"] = "some-device.local"

    with pytest.raises(ValueError):
        store.insert_sample(data)


def test_limit_validation(store):
    with pytest.raises(ValueError):
        store.get_recent_samples(0)

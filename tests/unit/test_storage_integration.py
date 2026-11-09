from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from backend.app.services.client_registry import AnonymousClientRegistry
from gateway.accounting import (
    PerClientAccountingCollector,
    SysfsCounterReader,
    build_lab_inventory,
)
from network.telemetry.metrics_store import MetricsStore


T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def legacy_sample(**overrides):
    sample = {
        "recorded_at": T0.isoformat(),
        "interface_label": "Wi-Fi",
        "download_mbps": 12.5,
        "upload_mbps": 2.5,
        "adapter_up": True,
        "internet_reachable": True,
        "probe_target": "1.1.1.1",
        "probes_sent": 10,
        "probes_received": 9,
        "packet_loss_percent": 10.0,
        "rtt_min_ms": 10.0,
        "rtt_avg_ms": 15.0,
        "rtt_max_ms": 20.0,
        "rtt_jitter_avg_ms": 2.5,
    }
    sample.update(overrides)
    return sample


@pytest.fixture
def store(tmp_path):
    return MetricsStore(tmp_path / "integration.sqlite3")


def write_counters(root: Path, client: int, *, tx: int, rx: int):
    statistics = root / f"veth-c{client}-br" / "statistics"
    statistics.mkdir(parents=True, exist_ok=True)
    (statistics / "tx_bytes").write_text(str(tx))
    (statistics / "rx_bytes").write_text(str(rx))
    (statistics / "tx_packets").write_text(str(tx // 100))
    (statistics / "rx_packets").write_text(str(rx // 100))


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def test_windows_host_sample_is_written_to_canonical_history(store):
    sample_id = store.insert_sample(legacy_sample())

    history = store.get_aggregate_history(order="oldest")
    assert sample_id == 1
    assert len(history) == 1
    stored = history[0]
    assert stored.legacy_sample_id == sample_id
    assert stored.observation.metadata.source == "windows_host"
    assert stored.observation.metadata.scope == "aggregate_gateway"
    assert stored.observation.metadata.environment == "physical_host"
    assert stored.observation.metadata.quality == "measured"
    assert stored.observation.metadata.client_id is None
    assert stored.observation.metadata.observed_at == T0
    assert stored.observation.download_mbps == 12.5
    assert stored.observation.upload_mbps == 2.5
    assert stored.observation.rtt_ms == 15.0
    assert stored.observation.rtt_variation_ms == 2.5
    assert stored.observation.packet_loss_percent == 10.0
    assert store.count_samples() == 1
    assert store.get_recent_samples()[0]["rtt_min_ms"] == 10.0


def test_hotspot_sample_remains_aggregate_and_separate_from_clients(store):
    store.insert_sample(
        legacy_sample(
            interface_label="hotspot-aggregate",
            download_mbps=4.0,
            upload_mbps=1.0,
            packet_loss_percent=None,
            rtt_min_ms=None,
            rtt_avg_ms=None,
            rtt_max_ms=None,
            rtt_jitter_avg_ms=None,
        )
    )

    history = store.get_aggregate_history()
    assert len(history) == 1
    stored = history[0]
    assert stored.observation.metadata.source == "windows_hotspot"
    assert stored.observation.metadata.scope == "aggregate_hotspot"
    assert stored.observation.metadata.client_id is None
    assert stored.observation.download_mbps == 4.0
    assert stored.observation.upload_mbps == 1.0
    assert stored.observation.rtt_ms is None
    assert store.get_client_history("client-0123456789abcdef", limit=10) == []


def test_replaying_migration_does_not_duplicate_new_samples(store, tmp_path):
    first = store.insert_sample(legacy_sample())
    second = store.insert_sample(
        legacy_sample(interface_label="hotspot-aggregate")
    )

    connection = sqlite3.connect(store.db_path)
    try:
        connection.execute("PRAGMA user_version = 0")
        connection.commit()
    finally:
        connection.close()

    reopened = MetricsStore(store.db_path)
    history = reopened.get_aggregate_history(order="oldest")

    assert len(history) == 2
    assert [item.legacy_sample_id for item in history] == [first, second]
    assert reopened.count_samples() == 2


def test_failed_canonical_write_rolls_back_legacy_row(store, monkeypatch):
    def fail(_observation):
        raise RuntimeError("forced canonical failure")

    monkeypatch.setattr(store, "_observation_values", fail)

    with pytest.raises(RuntimeError, match="forced canonical failure"):
        store.insert_sample(legacy_sample())

    assert store.count_samples() == 0
    assert store.count_observations() == 0


def test_malformed_timestamp_is_rejected_before_any_write(store):
    with pytest.raises(ValueError, match="Invalid timestamp"):
        store.insert_sample(legacy_sample(recorded_at="not-a-timestamp"))

    assert store.count_samples() == 0
    assert store.count_observations() == 0


def test_linux_collector_observations_persist_without_fabricating_rates(tmp_path):
    sysfs = tmp_path / "sys-class-net"
    store = MetricsStore(tmp_path / "lab.sqlite3")
    registry = AnonymousClientRegistry()
    inventory = build_lab_inventory(registry, client_numbers=(1, 2))
    clock = Clock()
    collector = PerClientAccountingCollector(
        inventory,
        registry,
        reader=SysfsCounterReader(sysfs),
        monotonic=clock,
    )

    for config in inventory:
        store.register_client(
            config.client_id,
            f"Client {config.client_number:02d}",
            environment="simulated_lab",
            simulated_lab_slot=config.client_number,
        )

    write_counters(sysfs, 1, tx=1_000, rx=500)
    write_counters(sysfs, 2, tx=1_000, rx=500)
    first = collector.collect(now=T0)
    store.save_observations([item.observation for item in first])

    assert all(
        item.observation.download_mbps is None for item in first
    )
    assert all(
        item.observation.metadata.collector_error
        == "rate_unavailable:no_baseline"
        for item in first
    )

    write_counters(sysfs, 1, tx=2_000, rx=500)
    clock.value = 1.0
    second = collector.collect(now=T0 + timedelta(seconds=1))
    store.save_observations([item.observation for item in second])

    write_counters(sysfs, 1, tx=500, rx=500)
    clock.value = 2.0
    third = collector.collect(now=T0 + timedelta(seconds=2))
    store.save_observations([item.observation for item in third])

    client_one = store.get_client_history(inventory[0].client_id, order="oldest")
    client_two = store.get_client_history(inventory[1].client_id, order="oldest")

    assert len(client_one) == 3
    assert len(client_two) == 3
    assert client_one[0].observation.download_mbps is None
    assert client_one[0].observation.metadata.quality == "unavailable"
    assert (
        client_one[0].observation.metadata.collector_error
        == "rate_unavailable:no_baseline"
    )
    assert client_one[1].observation.download_mbps == pytest.approx(0.008)
    assert client_one[1].observation.metadata.quality == "measured"
    assert client_one[1].observation.metadata.collector_error is None
    assert client_one[2].observation.download_mbps is None
    assert (
        client_one[2].observation.metadata.collector_error
        == "rate_unavailable:counter_reset"
    )

    assert client_two[1].observation.download_mbps == 0.0
    assert client_two[1].observation.upload_mbps == 0.0
    assert client_two[1].observation.metadata.quality == "measured"

    all_rates = [
        item.observation.download_mbps
        for item in client_one + client_two
        if item.observation.download_mbps is not None
    ]
    assert all(rate >= 0 for rate in all_rates)
    assert store.get_aggregate_history(limit=10) == []


def test_simulated_client_grouping_survives_store_restart(tmp_path):
    sysfs = tmp_path / "sys-class-net"
    database_path = tmp_path / "lab.sqlite3"
    store = MetricsStore(database_path)
    registry = AnonymousClientRegistry()
    inventory = build_lab_inventory(registry, client_numbers=(1, 2))
    clock = Clock()
    collector = PerClientAccountingCollector(
        inventory,
        registry,
        reader=SysfsCounterReader(sysfs),
        monotonic=clock,
    )

    for config in inventory:
        store.register_client(
            config.client_id,
            f"Client {config.client_number:02d}",
            environment="simulated_lab",
            simulated_lab_slot=config.client_number,
        )

    write_counters(sysfs, 1, tx=1_000, rx=500)
    write_counters(sysfs, 2, tx=2_000, rx=500)
    first = collector.collect(now=T0)
    store.save_observations([item.observation for item in first])

    write_counters(sysfs, 1, tx=3_000, rx=500)
    write_counters(sysfs, 2, tx=2_000, rx=500)
    clock.value = 1.0
    second = collector.collect(now=T0 + timedelta(seconds=1))
    store.save_observations([item.observation for item in second])

    reopened = MetricsStore(database_path)
    slot_one = reopened.get_simulated_client_by_slot(1)
    slot_two = reopened.get_simulated_client_by_slot(2)

    assert slot_one.client_id == inventory[0].client_id
    assert slot_two.client_id == inventory[1].client_id
    assert slot_one.environment == "simulated_lab"
    assert len(reopened.get_client_history(slot_one.client_id)) == 2
    assert len(reopened.get_client_history(slot_two.client_id)) == 2

    first_ids = {
        item.observation.metadata.client_id
        for item in reopened.get_client_history(slot_one.client_id)
    }
    assert first_ids == {inventory[0].client_id}

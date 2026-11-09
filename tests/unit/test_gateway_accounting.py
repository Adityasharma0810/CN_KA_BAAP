from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.services.client_registry import AnonymousClientRegistry
from gateway.accounting import (
    ClientCounterSnapshot,
    LabClientConfig,
    PerClientAccountingCollector,
    RateResult,
    SysfsCounterReader,
    build_lab_inventory,
    calculate_client_rates,
)


T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def counter(rx_b, tx_b, rx_p=1, tx_p=1, at=T0):
    return ClientCounterSnapshot(rx_b, tx_b, rx_p, tx_p, at)


def test_existing_topology_builds_three_and_five_client_inventories():
    registry = AnonymousClientRegistry()
    three = build_lab_inventory(registry, client_numbers=(1, 2, 3))
    five = build_lab_inventory(registry, client_numbers=(1, 2, 3, 4, 5))

    assert [client.gateway_interface for client in three] == [
        "veth-c1-br", "veth-c2-br", "veth-c3-br"
    ]
    assert [client.namespace_name for client in five] == [
        "client1", "client2", "client3", "client4", "client5"
    ]
    assert len({client.client_id for client in five}) == 5


def test_inventory_rejects_duplicate_or_malformed_configuration():
    registry = AnonymousClientRegistry()
    first, second = registry.register(), registry.register()
    with pytest.raises(ValueError, match="duplicate"):
        PerClientAccountingCollector(
            [
                LabClientConfig(1, first.client_id, "client1", "veth-c1-br"),
                LabClientConfig(1, second.client_id, "client1", "veth-c1-br"),
            ],
            registry,
        )
    with pytest.raises(ValueError, match="does not match"):
        LabClientConfig(2, first.client_id, "client1", "veth-c1-br")


def test_rate_formula_and_direction():
    result = calculate_client_rates(counter(100, 200), counter(1_100, 2_200), 2.0)

    assert result == RateResult(0.008, 0.004, True)


def test_first_sample_reset_and_invalid_elapsed_are_unavailable():
    current = counter(100, 200)
    assert calculate_client_rates(None, current, 1.0).reason == "no_baseline"
    assert calculate_client_rates(counter(200, 300), current, 1.0).reason == "counter_reset"
    with pytest.raises(ValueError):
        calculate_client_rates(counter(1, 1), current, 0)
    with pytest.raises(ValueError):
        calculate_client_rates(counter(1, 1), current, "bad")


def test_sysfs_reader_reads_all_byte_and_packet_counters(tmp_path: Path):
    stats = tmp_path / "veth-c1-br" / "statistics"
    stats.mkdir(parents=True)
    values = {
        "rx_bytes": "10\n", "tx_bytes": "20\n",
        "rx_packets": "3\n", "tx_packets": "4\n",
    }
    for name, value in values.items():
        (stats / name).write_text(value)

    snapshot = SysfsCounterReader(tmp_path)("veth-c1-br", T0)
    assert snapshot == counter(10, 20, 3, 4)


def test_collector_isolates_client_counters_and_keeps_idle_zero():
    registry = AnonymousClientRegistry()
    inventory = build_lab_inventory(registry, client_numbers=(1, 2, 3))
    samples = {
        "veth-c1-br": [counter(0, 0, 0, 0), counter(0, 1_000, 0, 10)],
        "veth-c2-br": [counter(0, 0, 0, 0), counter(500, 0, 5, 0)],
        "veth-c3-br": [counter(0, 0, 0, 0), counter(0, 0, 0, 0)],
    }
    indexes = {key: 0 for key in samples}
    clock = iter((10.0, 12.0))

    def reader(interface, observed_at):
        value = samples[interface][indexes[interface]]
        indexes[interface] += 1
        return value

    collector = PerClientAccountingCollector(
        inventory, registry, reader=reader, monotonic=lambda: next(clock)
    )
    first = collector.collect(now=T0)
    second = collector.collect(now=T0.replace(second=2))

    assert all(item.observation.download_mbps is None for item in first)
    by_id = {item.client_id: item.observation for item in second}
    assert by_id[inventory[0].client_id].download_bytes == 1_000
    assert by_id[inventory[0].client_id].upload_bytes == 0
    assert by_id[inventory[0].client_id].download_mbps == 0.004
    assert by_id[inventory[1].client_id].upload_mbps == 0.002
    assert by_id[inventory[2].client_id].download_mbps == 0
    assert by_id[inventory[2].client_id].upload_mbps == 0
    assert all(item.observation.metadata.client_id for item in second)
    assert all(registry.get(item.client_id, now=T0.replace(second=2)).status == "online" for item in second)


def test_counter_reset_and_missing_interface_do_not_stop_other_clients():
    registry = AnonymousClientRegistry()
    inventory = build_lab_inventory(registry, client_numbers=(1, 2, 3))
    readings = {
        "veth-c1-br": counter(100, 100),
        "veth-c2-br": counter(10, 10),
        "veth-c3-br": counter(0, 0),
    }

    def reader(interface, observed_at):
        if interface == "veth-c2-br":
            raise RuntimeError("counter interface unavailable")
        return readings[interface]

    collector = PerClientAccountingCollector(inventory, registry, reader=reader, monotonic=lambda: 1.0)
    first = collector.collect(now=T0)
    assert all(item.observation.metadata.quality == "unavailable" for item in first)

    readings["veth-c1-br"] = counter(0, 100)
    readings["veth-c3-br"] = counter(0, 50)
    second = collector.collect(now=T0.replace(second=1))
    by_id = {item.client_id: item for item in second}
    assert by_id[inventory[1].client_id].rate_reason == "interface_unavailable"
    assert by_id[inventory[0].client_id].observation.metadata.quality == "unavailable"
    assert by_id[inventory[2].client_id].observation.metadata.quality == "unavailable"


def test_results_do_not_expose_lab_infrastructure_or_private_identity_fields():
    registry = AnonymousClientRegistry()
    client = registry.register()
    config = LabClientConfig(1, client.client_id, "client1", "veth-c1-br")
    collector = PerClientAccountingCollector(
        [config], registry, reader=lambda interface, at: counter(1, 2), monotonic=lambda: 1.0
    )
    result = collector.collect(now=T0)[0].observation.model_dump(mode="json")
    serialized = str(result).lower()

    assert "client_id" in result["metadata"]
    assert "192.168" not in serialized
    assert "mac" not in serialized
    assert "device" not in serialized
    assert "veth-c1-br" not in serialized

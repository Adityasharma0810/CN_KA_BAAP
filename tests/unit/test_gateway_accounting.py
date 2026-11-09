import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

import gateway.collector as collector_module
from backend.app.services.client_registry import AnonymousClientRegistry
from gateway.accounting import (
    ClientCounterSnapshot,
    LabClientConfig,
    PerClientAccountingCollector,
    RateResult,
    SysfsCounterReader,
    build_lab_inventory,
    calculate_client_rates,
    client_numbers_from_environment,
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


def test_inventory_reuses_registry_labels_when_growing_from_three_to_five():
    registry = AnonymousClientRegistry()
    three = build_lab_inventory(registry, client_numbers=(1, 2, 3))
    five = build_lab_inventory(registry, client_numbers=(1, 2, 3, 4, 5))

    assert five[:3] == three
    assert len(registry.list_clients()) == 5
    assert [client.client_id for client in five] == [
        client.client_id for client in registry.list_clients()
    ]


def test_inventory_and_environment_reject_invalid_client_counts():
    registry = AnonymousClientRegistry()
    for values in ((), (0,), (-1,), (True,), (1, "2"), (100,)):
        with pytest.raises(ValueError):
            build_lab_inventory(registry, client_numbers=values)

    assert client_numbers_from_environment({}) == (1, 2, 3)
    assert client_numbers_from_environment({"EB_LAB_CLIENTS": "5"}) == (1, 2, 3, 4, 5)
    for value in ("0", "-1", "abc", "1.5", "100"):
        with pytest.raises(ValueError):
            client_numbers_from_environment({"EB_LAB_CLIENTS": value})


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
    with pytest.raises(ValueError, match="numeric"):
        calculate_client_rates(counter(1, 1), current, True)
    with pytest.raises(ValueError, match="numeric"):
        calculate_client_rates(counter(1, 1), current, None)
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="finite"):
            calculate_client_rates(counter(1, 1), current, value)


def test_counter_snapshot_rejects_non_datetime_timestamp():
    with pytest.raises(ValueError, match="datetime"):
        ClientCounterSnapshot(1, 1, 1, 1, "2026-11-09T12:00:00Z")


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


def test_collector_rebases_after_a_stalled_monotonic_clock():
    registry = AnonymousClientRegistry()
    inventory = build_lab_inventory(registry, client_numbers=(1,))
    samples = iter((counter(0, 0), counter(100, 200), counter(200, 400)))
    clock = iter((5.0, 5.0, 6.0))
    collector = PerClientAccountingCollector(
        inventory,
        registry,
        reader=lambda interface, at: next(samples),
        monotonic=lambda: next(clock),
    )

    assert collector.collect(now=T0)[0].rate_reason == "no_baseline"
    stalled = collector.collect(now=T0.replace(second=1))[0]
    assert stalled.rate_reason == "invalid_elapsed"
    recovered = collector.collect(now=T0.replace(second=2))[0]
    assert recovered.rate_reason is None
    assert recovered.observation.download_mbps == 0.0016
    assert recovered.observation.upload_mbps == 0.0008


def test_legacy_read_bytes_delegates_to_the_shared_sysfs_reader(monkeypatch):
    calls = []

    def fake_reader(interface, observed_at=None):
        calls.append(interface)
        return counter(11, 22, 3, 4)

    assert isinstance(collector_module._counter_reader, SysfsCounterReader)
    monkeypatch.setattr(collector_module, "_counter_reader", fake_reader)

    assert collector_module.read_bytes(1) == (22, 11)
    assert calls == ["veth-c1-br"]
    with pytest.raises(ValueError, match="Unknown lab client"):
        collector_module.read_bytes(99)

    source = inspect.getsource(collector_module.read_bytes)
    assert "/sys/class/net" not in source
    assert "read_text" not in source


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

import asyncio
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from threading import Event, Lock

import pytest

from backend.app.models.schemas import TelemetryObservation
from backend.app.services.client_registry import AnonymousClientRegistry
from backend.app.services.lab_ingest_service import LabIngestService
from backend.app.services.lab_accounting_service import LabAccountingService
from backend.app.services.observation_query_service import build_current_observations
from backend.app.services.topology_service import TopologyService
from gateway.accounting import LabClientConfig
from network.telemetry.metrics_store import MetricsStore


NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def run_async(test):
    @wraps(test)
    def wrapper(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))

    return wrapper


class FakeAccounting:
    def __init__(self, *, available=True, failing=False):
        self.registry = AnonymousClientRegistry()
        self.inventory = tuple(
            LabClientConfig(
                number,
                self.registry.register().client_id,
                f"client{number}",
                f"veth-c{number}-br",
            )
            for number in (1, 2)
        )
        self.available = available
        self.failing = failing
        self.calls = 0

    def is_available(self):
        return self.available

    def collect(self):
        self.calls += 1
        if self.failing:
            raise RuntimeError("/private/path must only be logged")
        if not self.available:
            return {"available": False, "clients": []}
        clients = []
        for index, config in enumerate(self.inventory):
            observation = TelemetryObservation(
                metadata={
                    "observed_at": NOW,
                    "source": "linux_namespace_lab",
                    "scope": "client",
                    "quality": "measured",
                    "environment": "simulated_lab",
                    "client_id": config.client_id,
                },
                download_bytes=1000 * (index + 1),
                upload_bytes=500 * (index + 1),
                download_packets=10 * (index + 1),
                upload_packets=5 * (index + 1),
                download_mbps=1.25 * (index + 1),
                upload_mbps=0.25 * (index + 1),
            )
            clients.append(
                {"client_id": config.client_id, "observation": observation.model_dump(mode="json")}
            )
        return {"available": True, "clients": clients}


def _worker(tmp_path, accounting=None, **options):
    database = tmp_path / "ingest.sqlite3"
    worker = LabIngestService(
        accounting=accounting or FakeAccounting(),
        db_path_provider=lambda: database,
        clock=lambda: NOW,
        platform_name="linux",
        enabled=True,
        **options,
    )
    return worker, database


@run_async
async def test_success_persists_client_and_aggregate_observations(tmp_path):
    accounting = FakeAccounting()
    worker, database = _worker(tmp_path, accounting=accounting)

    result = await worker.collect_once()
    store = MetricsStore(database)
    clients = store.get_history_by_source(
        "linux_namespace_lab", scope="client", order="oldest"
    )
    gateway = store.get_history_by_source(
        "linux_gateway", scope="aggregate_gateway", limit=1
    )
    stored_text = str(
        [
            item.observation.model_dump(mode="json")
            for item in [*clients, *gateway]
        ]
    )

    assert result.error_code is None
    assert len(clients) == 2
    assert len(gateway) == 1
    assert gateway[0].observation.download_mbps == 3.75
    assert gateway[0].observation.upload_mbps == 0.75
    assert gateway[0].observation.metadata.quality == "derived"
    assert all(
        store.get_simulated_client_by_slot(slot) is not None
        for slot in (1, 2)
    )
    assert accounting.registry.list_clients(now=NOW)[0].status == "online"
    for private_identifier in (
        "client1",
        "client2",
        "veth-c1-br",
        "br-lab",
        "/sys/class/net",
    ):
        assert private_identifier not in stored_text


@run_async
async def test_topology_reflects_ingested_lab_and_empty_database(tmp_path):
    accounting = FakeAccounting()
    worker, database = _worker(tmp_path, accounting=accounting)
    service = TopologyService(
        db_path=database,
        clock=lambda: NOW,
        registry=accounting.registry,
    )

    empty = service.network_topology()
    assert next(node for node in empty.nodes if node.node_id == "linux-lab").state == "missing"

    await worker.collect_once()
    topology = service.network_topology()
    lab = next(node for node in topology.nodes if node.node_id == "linux-lab")
    clients = [node for node in topology.nodes if node.kind == "client"]

    assert lab.state == "online"
    assert len(clients) == 2
    assert all(node.state == "online" for node in clients)
    current = build_current_observations(database, scope="client")
    assert {
        node.client_id for node in clients
    } == {
        item.observation.metadata.client_id
        for item in current.observations
    }


@run_async
async def test_unavailable_rate_samples_keep_nulls_and_measured_zero(tmp_path):
    accounting = FakeAccounting()
    worker, database = _worker(tmp_path, accounting=accounting)
    accounting.collect = lambda: {
        "available": True,
        "clients": [
            {
                "observation": TelemetryObservation(
                    metadata={
                        "observed_at": NOW,
                        "source": "linux_namespace_lab",
                        "scope": "client",
                        "quality": "unavailable",
                        "environment": "simulated_lab",
                        "collector_error": "rate_unavailable:no_baseline",
                        "client_id": item.client_id,
                    },
                    download_mbps=None,
                    upload_mbps=None,
                ).model_dump(mode="json")
            }
            for item in accounting.inventory
        ],
    }

    result = await worker.collect_once()
    store = MetricsStore(database)
    client_rows = store.get_history_by_source(
        "linux_namespace_lab", scope="client", order="oldest"
    )
    gateway = store.get_history_by_source("linux_gateway", limit=1)[0].observation

    assert result.error_code == "rate_baseline_pending"
    assert all(row.observation.download_mbps is None for row in client_rows)
    assert gateway.download_mbps is None
    assert gateway.metadata.quality == "unavailable"

    class ZeroAccounting(FakeAccounting):
        def collect(self):
            response = super().collect()
            for item in response["clients"]:
                observation = TelemetryObservation.model_validate(item["observation"])
                item["observation"] = observation.model_copy(
                    update={"download_mbps": 0.0, "upload_mbps": 0.0}
                ).model_dump(mode="json")
            return response

    zero_worker, zero_database = _worker(tmp_path / "zero", accounting=ZeroAccounting())
    zero_result = await zero_worker.collect_once()
    zero_store = MetricsStore(zero_database)
    zero_gateway = zero_store.get_history_by_source("linux_gateway", limit=1)[0]
    assert zero_result.error_code is None
    assert zero_gateway.observation.download_mbps == 0.0
    assert zero_gateway.observation.upload_mbps == 0.0


@run_async
async def test_counter_reset_does_not_create_rates(tmp_path):
    accounting = FakeAccounting()
    worker, database = _worker(tmp_path, accounting=accounting)
    accounting.collect = lambda: {
        "available": True,
        "clients": [
            {
                "observation": TelemetryObservation(
                    metadata={
                        "observed_at": NOW,
                        "source": "linux_namespace_lab",
                        "scope": "client",
                        "quality": "unavailable",
                        "environment": "simulated_lab",
                        "collector_error": "rate_unavailable:counter_reset",
                        "client_id": item.client_id,
                    },
                    download_mbps=None,
                    upload_mbps=None,
                    download_bytes=0,
                    upload_bytes=0,
                ).model_dump(mode="json")
            }
            for item in accounting.inventory
        ],
    }

    result = await worker.collect_once()
    store = MetricsStore(database)
    rows = store.get_history_by_source(
        "linux_namespace_lab", scope="client", order="oldest"
    )

    assert result.error_code == "counter_reset"
    assert all(row.observation.download_mbps is None for row in rows)
    assert all(row.observation.upload_mbps is None for row in rows)


@run_async
async def test_lab_failure_is_persisted_as_unavailable_then_recovers(tmp_path):
    accounting = FakeAccounting(available=False)
    worker, database = _worker(tmp_path, accounting=accounting)

    failed = await worker.collect_once()
    failed_gateway = MetricsStore(database).get_history_by_source(
        "linux_gateway", limit=1
    )[0].observation
    accounting.available = True
    recovered = await worker.collect_once()
    recovered_gateway = MetricsStore(database).get_history_by_source(
        "linux_gateway", limit=1
    )[0].observation

    assert failed.error_code == "lab_not_available"
    assert failed_gateway.metadata.quality == "unavailable"
    assert recovered.error_code is None
    assert recovered_gateway.metadata.quality == "derived"
    assert worker.last_error_code is None


@run_async
async def test_collection_exception_is_safe_and_does_not_leak_details(tmp_path):
    worker, database = _worker(
        tmp_path,
        accounting=FakeAccounting(failing=True),
    )
    result = await worker.collect_once()
    rows = MetricsStore(database).get_history_by_source("linux_gateway", limit=1)

    assert result.error_code == "collection_failed"
    assert rows[0].observation.metadata.collector_error == "collection_failed"
    assert "/private/path" not in str(rows[0].observation.model_dump())


@run_async
async def test_worker_backoff_caps_at_thirty_seconds(tmp_path):
    delays = []
    worker, _ = _worker(
        tmp_path,
        accounting=FakeAccounting(failing=True),
        interval_seconds=10,
    )

    async def stop_after_five(delay):
        delays.append(delay)
        if len(delays) == 5:
            raise asyncio.CancelledError

    worker.sleep = stop_after_five
    worker.start()
    assert worker._task is not None
    with pytest.raises(asyncio.CancelledError):
        await worker._task
    await worker.stop()

    assert delays == [10, 20, 30, 30, 30]


@run_async
async def test_cycles_do_not_overlap_and_shutdown_waits_for_active_cycle(tmp_path):
    accounting = FakeAccounting()
    entered = Event()
    release = Event()
    guard = Lock()
    active = 0
    maximum_active = 0
    original_collect = accounting.collect

    def blocking_collect():
        nonlocal active, maximum_active
        with guard:
            active += 1
            maximum_active = max(maximum_active, active)
        entered.set()
        release.wait(timeout=2)
        result = original_collect()
        with guard:
            active -= 1
        return result

    accounting.collect = blocking_collect
    worker, _ = _worker(tmp_path, accounting=accounting, interval_seconds=1)
    worker.start()
    assert await asyncio.to_thread(entered.wait, 1)
    stopping = asyncio.create_task(worker.stop())
    await asyncio.sleep(0)
    release.set()
    await stopping

    assert maximum_active == 1
    assert active == 0
    assert worker._task is None


def test_default_ingest_is_disabled_off_linux_or_without_lab(monkeypatch):
    monkeypatch.delenv("EB_LAB_INGEST", raising=False)
    missing_lab = FakeAccounting(available=False)
    worker = LabIngestService(
        accounting=missing_lab,
        platform_name="linux",
        enabled=None,
    )
    other_platform = LabIngestService(
        accounting=FakeAccounting(),
        platform_name="other",
        enabled=None,
    )

    assert worker.enabled is False
    assert worker.last_error_code == "lab_not_available"
    assert other_platform.enabled is False
    assert other_platform.last_error_code == "not_supported_on_platform"


def test_startup_survives_lab_availability_probe_failure():
    class BrokenAvailability(FakeAccounting):
        def is_available(self):
            raise RuntimeError("/private/path must not escape startup")

    worker = LabIngestService(
        accounting=BrokenAvailability(),
        platform_name="linux",
        enabled=None,
    )

    assert worker.enabled is False
    assert worker.last_error_code == "lab_not_available"


def test_registry_restores_client_ids_for_same_lab_slots_after_restart(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("EB_LAB_CLIENTS", "3")
    store = MetricsStore(tmp_path / "restart.sqlite3")
    initial_service = LabAccountingService()
    initial_ids = {}
    for client in initial_service.inventory:
        registered = initial_service.registry.get(client.client_id)
        store.register_client(
            client.client_id,
            registered.display_label,
            environment="simulated_lab",
            simulated_lab_slot=client.client_number,
        )
        initial_ids[client.client_number] = client.client_id

    restarted_service = LabAccountingService()
    persisted_ids = {
        slot: store.get_simulated_client_by_slot(slot).client_id
        for slot in initial_ids
    }
    restarted_service.configure_persisted_clients(persisted_ids)

    assert {
        client.client_number: client.client_id
        for client in restarted_service.inventory
    } == initial_ids


def test_interval_is_configurable_and_never_below_one_second():
    assert LabIngestService(
        accounting=FakeAccounting(),
        platform_name="linux",
        enabled=True,
        interval_seconds=1,
    ).interval_seconds == 1

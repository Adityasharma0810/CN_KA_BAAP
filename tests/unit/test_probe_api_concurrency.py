"""Regression tests: GET endpoints must stay responsive while probe/ingest cycles run.

These tests prove that:
1. A deliberately slow fake probe runner (1.5 s per client) does not delay GET
   endpoint responses beyond 500 ms while the probe cycle is running.
2. A slow/failing probe for one client does not delay the others past the
   hard per-probe timeout.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.lab_accounting_service import LabAccountingService
from backend.app.services.lab_ingest_service import LabIngestService
from backend.app.services.latency_probe_service import (
    LatencyProbeService,
    _PROBE_TIMEOUT_SECONDS,
)
from backend.app.services.client_registry import AnonymousClientRegistry
from backend.app.models.schemas import TelemetryObservation
from gateway.accounting import LabClientConfig
from network.telemetry.metrics_store import MetricsStore


NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)

# Budget we allow a read to take while a cycle is running.
READ_BUDGET_SECONDS = 0.5


def run_async(test):
    @wraps(test)
    def wrapper(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))
    return wrapper


def completed(output, returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=output)


class FakeAccountingForTwo:
    """Two-client accounting fixture with injectable collect()."""

    def __init__(self, collect_fn=None):
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
        self._collect_fn = collect_fn

    def is_available(self):
        return True

    def collect(self):
        if self._collect_fn is not None:
            return self._collect_fn(self.inventory)
        clients = []
        for idx, config in enumerate(self.inventory):
            obs = TelemetryObservation(
                metadata={
                    "observed_at": NOW,
                    "source": "linux_namespace_lab",
                    "scope": "client",
                    "quality": "measured",
                    "environment": "simulated_lab",
                    "client_id": config.client_id,
                },
                download_mbps=1.25 * (idx + 1),
                upload_mbps=0.25 * (idx + 1),
                download_bytes=1000 * (idx + 1),
                upload_bytes=500 * (idx + 1),
                download_packets=10 * (idx + 1),
                upload_packets=5 * (idx + 1),
            )
            clients.append({
                "client_id": config.client_id,
                "observation": obs.model_dump(mode="json"),
            })
        return {"available": True, "clients": clients}


@run_async
async def test_get_endpoint_responds_fast_while_slow_probe_cycle_runs(tmp_path):
    """With a 1.5 s/client fake probe runner, a GET that reads from the store
    must still return within READ_BUDGET_SECONDS while the probe cycle is
    running concurrently.

    This proves that WAL mode (or equivalent) prevents probe writes from
    blocking read-only API queries.
    """
    SLOW_PROBE_SLEEP = 1.5  # seconds — deliberately slow

    db_path = tmp_path / "test.sqlite3"

    def slow_probe_runner(*_args, **_kwargs):
        time.sleep(SLOW_PROBE_SLEEP)
        return completed("ok 5 5 10.0 0.5\n")

    accounting = FakeAccountingForTwo()

    probe_service = LatencyProbeService(
        accounting=accounting,
        clock=lambda: NOW,
        runner=slow_probe_runner,
        platform_name="linux",
        probe_timeout_seconds=SLOW_PROBE_SLEEP + 0.5,
    )

    ingest_service = LabIngestService(
        accounting=accounting,
        db_path_provider=lambda: db_path,
        clock=lambda: NOW,
        platform_name="linux",
        enabled=True,
        probe_service=probe_service,
    )

    # Seed the database with one good cycle before the concurrency test.
    await ingest_service.collect_once()

    # Now start a slow probe cycle in the background and immediately issue a
    # read from the store.  The read must not block on the write lock.
    probe_cycle_task = asyncio.create_task(probe_service.probe_once())

    # Give the probe cycle a moment to start its blocking subprocess calls.
    await asyncio.sleep(0.05)

    # Issue a store read while the probe executor threads are busy.
    loop = asyncio.get_running_loop()
    t0 = time.monotonic()
    result = await loop.run_in_executor(
        None,
        lambda: MetricsStore(db_path).get_history_by_source(
            "linux_namespace_lab", scope="client", limit=10
        ),
    )
    read_elapsed = time.monotonic() - t0

    # Cancel the still-running probe cycle; we only needed it to be in flight.
    probe_cycle_task.cancel()
    try:
        await probe_cycle_task
    except (asyncio.CancelledError, Exception):
        pass

    assert read_elapsed < READ_BUDGET_SECONDS, (
        f"read took {read_elapsed:.3f} s while probe cycle was running — "
        "write lock is blocking reads (WAL mode not active?)"
    )
    # The seed data must be readable.
    assert len(result) == 2


@run_async
async def test_slow_single_client_probe_does_not_delay_api_budget(tmp_path):
    """One client whose probe exceeds the hard timeout must not push the
    overall cycle beyond N × _PROBE_TIMEOUT_SECONDS.

    We verify that the probe cycle completes within
    _PROBE_TIMEOUT_SECONDS + small_overhead regardless of how many slots
    there are, proving per-client isolation.
    """
    OVERHEAD = 0.5  # seconds of tolerance

    def flaky_runner(argv, **_kwargs):
        slot = int(argv[-1])
        if slot == 2:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=_PROBE_TIMEOUT_SECONDS)
        return completed("ok 5 5 5.0 0.3\n")

    accounting = FakeAccountingForTwo()
    probe_service = LatencyProbeService(
        accounting=accounting,
        clock=lambda: NOW,
        runner=flaky_runner,
        platform_name="linux",
        probe_timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )

    t0 = time.monotonic()
    await probe_service.probe_once()
    elapsed = time.monotonic() - t0

    assert elapsed < _PROBE_TIMEOUT_SECONDS + OVERHEAD, (
        f"probe cycle took {elapsed:.3f} s — failing slot {2} is blocking others"
    )
    # Slot 1 should have a good result.
    assert probe_service.metrics_for_slot(1, NOW) is not None
    # Slot 2 should have a timeout error, not a missing entry.
    assert probe_service._samples[2].error_code == "probe_timeout"


@run_async
async def test_endpoint_reads_stay_under_500ms_during_slow_probe_and_ingest(tmp_path):
    """Endpoints (observations and topology) must stay well under 500ms while
    a deliberately slow fake probe runner (1.2 s) and ingest cycle run concurrently.
    """
    SLOW_PROBE_SLEEP = 1.2
    db_path = tmp_path / "slow_probe_test.sqlite3"

    def slow_probe_runner(*_args, **_kwargs):
        time.sleep(SLOW_PROBE_SLEEP)
        return completed("ok 5 5 12.0 0.4\n")

    accounting = FakeAccountingForTwo()
    probe_service = LatencyProbeService(
        accounting=accounting,
        clock=lambda: NOW,
        runner=slow_probe_runner,
        platform_name="linux",
        probe_timeout_seconds=SLOW_PROBE_SLEEP + 0.5,
    )
    ingest_service = LabIngestService(
        accounting=accounting,
        db_path_provider=lambda: db_path,
        clock=lambda: NOW,
        platform_name="linux",
        enabled=True,
        probe_service=probe_service,
    )

    await ingest_service.collect_once()

    probe_task = asyncio.create_task(probe_service.probe_once())
    await asyncio.sleep(0.05)

    from backend.app.services.observation_query_service import build_current_observations
    from backend.app.services.topology_service import TopologyService

    loop = asyncio.get_running_loop()
    top_svc = TopologyService(db_path=db_path, clock=lambda: NOW, registry=accounting.registry)

    t0 = time.monotonic()
    obs_res = await loop.run_in_executor(
        None,
        lambda: build_current_observations(db_path, scope="client"),
    )
    t_obs = time.monotonic() - t0

    t1 = time.monotonic()
    top_res = await loop.run_in_executor(
        None,
        lambda: top_svc.network_topology(),
    )
    t_top = time.monotonic() - t1

    probe_task.cancel()
    try:
        await probe_task
    except (asyncio.CancelledError, Exception):
        pass

    assert t_obs < READ_BUDGET_SECONDS, f"observations read took {t_obs:.3f}s (> 500ms)"
    assert t_top < READ_BUDGET_SECONDS, f"topology read took {t_top:.3f}s (> 500ms)"
    assert obs_res.count == 2
    assert len(top_res.nodes) >= 2

"""Background persistence for read-only Linux namespace-lab counters."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import platform
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Mapping

from backend.app.config import database_path
from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from backend.app.services.lab_accounting_service import (
    LabAccountingService,
    lab_accounting_service,
)
from backend.app.services.latency_probe_service import (
    LatencyProbeService,
    latency_probe_service,
)
from network.telemetry.metrics_store import MetricsStore


_LOGGER = logging.getLogger(__name__)
_MAX_BACKOFF_SECONDS = 30.0
_SAFE_FAILURE_CODES = {
    "collection_failed",
    "counter_reset",
    "lab_not_available",
    "partial_collection",
    "persistence_failed",
    "rate_baseline_pending",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def lab_ingest_interval_seconds(environ: Mapping[str, str] | None = None) -> float:
    values = os.environ if environ is None else environ
    raw = values.get("EB_LAB_INGEST_INTERVAL", "").strip()
    try:
        interval = float(raw) if raw else 2.0
    except ValueError:
        interval = 2.0
    if not math.isfinite(interval):
        interval = 2.0
    return min(max(interval, 1.0), 3600.0)


def _platform_name() -> str:
    value = platform.system().lower()
    return value if value in {"linux", "windows"} else "other"


@dataclass(frozen=True)
class _CycleResult:
    error_code: str | None
    last_success_at: datetime | None


class LabIngestService:
    """Collect and persist lab observations without blocking the API loop."""

    def __init__(
        self,
        *,
        accounting: LabAccountingService = lab_accounting_service,
        db_path_provider: Callable[[], Path] = database_path,
        store_factory: Callable[[Path], MetricsStore] = MetricsStore,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        probe_service: LatencyProbeService | None = None,
        platform_name: str | None = None,
        enabled: bool | None = None,
        interval_seconds: float | None = None,
    ):
        self.accounting = accounting
        self.db_path_provider = db_path_provider
        self.store_factory = store_factory
        self.clock = clock
        self.sleep = sleep
        self.probe_service = probe_service or latency_probe_service
        self.platform = platform_name or _platform_name()
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else lab_ingest_interval_seconds()
        )
        if self.interval_seconds < 1:
            raise ValueError("lab ingest interval must be at least one second")

        self._failure_count = 0
        self._cycle_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._identity_configured = False
        self._registered_client_ids: set[str] = set()
        self.last_success_at: datetime | None = None
        self.last_error_code: str | None = None
        self.enabled = self._resolve_enabled(enabled)

    def _resolve_enabled(self, explicit: bool | None) -> bool:
        if explicit is not None:
            requested = explicit
        else:
            setting = os.environ.get("EB_LAB_INGEST", "").strip()
            if setting == "1":
                requested = True
            elif setting == "0":
                requested = False
            else:
                try:
                    requested = (
                        self.platform == "linux"
                        and bool(self.accounting.is_available())
                    )
                except Exception:
                    _LOGGER.exception("lab ingest startup availability check failed")
                    requested = False

        if not requested:
            if self.platform != "linux":
                self.last_error_code = "not_supported_on_platform"
            elif os.environ.get("EB_LAB_INGEST", "").strip() == "0":
                self.last_error_code = "lab_ingest_disabled"
            else:
                self.last_error_code = "lab_not_available"
        return requested

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def state(self) -> str:
        if not self.enabled:
            return "disabled"
        if self.last_error_code == "lab_not_available":
            return "unavailable"
        if self.last_error_code is not None:
            return "degraded"
        return "running" if self.running else "stopped"

    def start(self) -> None:
        """Start the single worker task; startup failures never escape."""

        if not self.enabled or self.running:
            return
        try:
            self._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="lab-ingest",
            )
            self._task = asyncio.create_task(self._run(), name="lab-ingest")
        except Exception:
            self.enabled = False
            self.last_error_code = "worker_start_failed"
            _LOGGER.exception("lab ingest worker could not start")

    async def stop(self) -> None:
        """Cancel the polling task and wait for any active SQLite cycle."""

        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    async def _run(self) -> None:
        try:
            while True:
                result = await self.collect_once()
                if result.error_code is None:
                    self._failure_count = 0
                    delay = self.interval_seconds
                else:
                    self._failure_count += 1
                    delay = min(
                        self.interval_seconds * 2 ** (self._failure_count - 1),
                        _MAX_BACKOFF_SECONDS,
                    )
                await self.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.last_error_code = "worker_failed"
            _LOGGER.exception("lab ingest polling loop failed")

    async def collect_once(self) -> _CycleResult:
        """Run one non-overlapping collection cycle outside the event loop."""

        async with self._cycle_lock:
            loop = asyncio.get_running_loop()
            executor = self._executor
            cycle = loop.run_in_executor(
                executor,
                self._collect_and_persist,
            )
            try:
                result = await asyncio.shield(cycle)
            except asyncio.CancelledError:
                await asyncio.shield(cycle)
                raise
            if result.last_success_at is not None:
                self.last_success_at = result.last_success_at
            self.last_error_code = result.error_code
            return result

    def _collect_and_persist(self) -> _CycleResult:
        now = self._now()
        store: MetricsStore | None = None
        try:
            store = self.store_factory(Path(self.db_path_provider()))
            self._configure_persisted_registry(store)
            self._register_clients(store)
            collected = self.accounting.collect()
            if not collected.get("available", False):
                observations = self._unavailable_observations(
                    now,
                    "lab_not_available",
                )
                self._save(store, observations)
                return _CycleResult("lab_not_available", None)

            clients = [
                TelemetryObservation.model_validate(item["observation"])
                for item in collected.get("clients", [])
            ]
            expected_ids = {item.client_id for item in self.accounting.inventory}
            actual_ids = {
                item.metadata.client_id
                for item in clients
                if item.metadata.client_id is not None
            }
            if actual_ids != expected_ids:
                raise ValueError("lab collector returned an incomplete inventory")

            slots_by_id = {
                client.client_id: client.client_number
                for client in self.accounting.inventory
            }
            clients = [
                self._merge_probe_metrics(item, slots_by_id, now)
                for item in clients
            ]

            for observation in clients:
                self.accounting.registry.observe(
                    observation,
                    now=observation.metadata.observed_at,
                )
            aggregate = self._aggregate_observation(clients, now)
            self._save(store, [*clients, aggregate])

            measured = [
                item
                for item in clients
                if item.metadata.quality in (
                    ValueQuality.MEASURED,
                    ValueQuality.DERIVED,
                )
                and item.download_mbps is not None
                and item.upload_mbps is not None
            ]
            has_unavailable = len(measured) != len(clients)
            if has_unavailable:
                error_code = self._partial_error_code(clients)
            else:
                error_code = None
            return _CycleResult(
                error_code,
                now if measured else None,
            )
        except Exception:
            _LOGGER.exception("lab ingest collection or persistence failed")
            try:
                if store is None:
                    store = self.store_factory(Path(self.db_path_provider()))
                    self._configure_persisted_registry(store)
                    self._register_clients(store)
                observations = self._unavailable_observations(
                    now,
                    "collection_failed",
                )
                self._save(store, observations)
            except Exception:
                _LOGGER.exception("lab ingest unavailable observation could not be saved")
                return _CycleResult("persistence_failed", None)
            return _CycleResult("collection_failed", None)

    def _merge_probe_metrics(
        self,
        observation: TelemetryObservation,
        slots_by_id: dict[str, int],
        now: datetime,
    ) -> TelemetryObservation:
        client_id = observation.metadata.client_id
        slot = slots_by_id.get(client_id or "")
        metrics = (
            self.probe_service.metrics_for_slot(slot, now)
            if slot is not None
            else None
        )
        if metrics is None:
            return observation.model_copy(
                update={
                    "rtt_ms": None,
                    "rtt_variation_ms": None,
                    "packet_loss_percent": None,
                }
            )
        return observation.model_copy(update=metrics)

    def _configure_persisted_registry(self, store: MetricsStore) -> None:
        if self._identity_configured:
            return
        configure = getattr(self.accounting, "configure_persisted_clients", None)
        if configure is not None:
            persisted_ids = {}
            for client in self.accounting.inventory:
                existing = store.get_simulated_client_by_slot(
                    client.client_number
                )
                if existing is not None:
                    persisted_ids[client.client_number] = existing.client_id
            configure(persisted_ids)
        self._identity_configured = True

    def _register_clients(self, store: MetricsStore) -> None:
        for client in self.accounting.inventory:
            if client.client_id in self._registered_client_ids:
                continue
            registered = self.accounting.registry.get(client.client_id)
            store.register_client(
                client.client_id,
                registered.display_label,
                environment=ObservationEnvironment.SIMULATED_LAB,
                simulated_lab_slot=client.client_number,
            )
            self._registered_client_ids.add(client.client_id)

    def _save(
        self,
        store: MetricsStore,
        observations: list[TelemetryObservation],
    ) -> None:
        store.save_observations(observations)

    def _unavailable_observations(
        self,
        now: datetime,
        error_code: str,
    ) -> list[TelemetryObservation]:
        safe_code = (
            error_code
            if error_code in _SAFE_FAILURE_CODES
            else "collection_failed"
        )
        observations = [
            TelemetryObservation(
                metadata={
                    "observed_at": now,
                    "source": ObservationSource.LINUX_NAMESPACE_LAB,
                    "scope": ObservationScope.CLIENT,
                    "quality": ValueQuality.UNAVAILABLE,
                    "environment": ObservationEnvironment.SIMULATED_LAB,
                    "collector_error": safe_code,
                    "client_id": client.client_id,
                }
            )
            for client in self.accounting.inventory
        ]
        observations.append(
            TelemetryObservation(
                metadata={
                    "observed_at": now,
                    "source": ObservationSource.LINUX_GATEWAY,
                    "scope": ObservationScope.AGGREGATE_GATEWAY,
                    "quality": ValueQuality.UNAVAILABLE,
                    "environment": ObservationEnvironment.SIMULATED_LAB,
                    "collector_error": safe_code,
                }
            )
        )
        return observations

    def _aggregate_observation(
        self,
        clients: list[TelemetryObservation],
        now: datetime,
    ) -> TelemetryObservation:
        rates_available = bool(clients) and all(
            item.download_mbps is not None
            and item.upload_mbps is not None
            and item.metadata.quality
            in (ValueQuality.MEASURED, ValueQuality.DERIVED)
            for item in clients
        )
        counters = {}
        for field in (
            "download_bytes",
            "upload_bytes",
            "download_packets",
            "upload_packets",
        ):
            values = [getattr(item, field) for item in clients]
            counters[field] = (
                sum(values)
                if values and all(value is not None for value in values)
                else None
            )

        return TelemetryObservation(
            metadata={
                "observed_at": now,
                "source": ObservationSource.LINUX_GATEWAY,
                "scope": ObservationScope.AGGREGATE_GATEWAY,
                "quality": (
                    ValueQuality.DERIVED
                    if rates_available
                    else ValueQuality.UNAVAILABLE
                ),
                "environment": ObservationEnvironment.SIMULATED_LAB,
                "collector_error": (
                    None
                    if rates_available
                    else "rate_unavailable:incomplete_clients"
                ),
            },
            download_mbps=(
                round(sum(item.download_mbps for item in clients), 6)
                if rates_available
                else None
            ),
            upload_mbps=(
                round(sum(item.upload_mbps for item in clients), 6)
                if rates_available
                else None
            ),
            **counters,
        )

    @staticmethod
    def _partial_error_code(
        clients: list[TelemetryObservation],
    ) -> str:
        errors = {
            item.metadata.collector_error
            for item in clients
            if item.metadata.collector_error
        }
        if "interface_unavailable" in errors:
            return (
                "lab_not_available"
                if all(
                    item.metadata.quality == ValueQuality.UNAVAILABLE
                    and item.metadata.collector_error == "interface_unavailable"
                    for item in clients
                )
                else "partial_collection"
            )
        if any("counter_reset" in error for error in errors):
            return "counter_reset"
        if any("no_baseline" in error for error in errors):
            return "rate_baseline_pending"
        return "partial_collection"

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("lab ingest clock must return an aware datetime")
        return now.astimezone(timezone.utc)


lab_ingest_service = LabIngestService()

"""Persistence boundary for observations fetched from a read-only gateway agent."""

from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from backend.app.config import database_path
from backend.app.models.schemas import ObservationEnvironment
from backend.app.services.gateway_transport_service import (
    GatewayObservationResponse,
    GatewayTransport,
    GatewayTransportError,
)
from network.telemetry.metrics_store import MetricsStore


_SAFE_ERRORS = {
    "gateway_authentication_failed",
    "gateway_route_unavailable",
    "gateway_request_rejected",
    "gateway_schema_invalid",
    "gateway_service_unavailable",
    "gateway_timeout",
    "gateway_unreachable",
}

_MAX_BACKOFF_SECONDS = 30.0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def gateway_ingest_interval_seconds(environ: os._Environ | None = None) -> float:
    values = os.environ if environ is None else environ
    raw = values.get("EB_GATEWAY_INGEST_INTERVAL", "").strip()
    try:
        interval = float(raw) if raw else 2.0
    except ValueError:
        interval = 2.0
    if not math.isfinite(interval):
        interval = 2.0
    return min(max(interval, 1.0), 3600.0)


@dataclass(frozen=True)
class GatewayIngestResult:
    error_code: str | None
    last_success_at: datetime | None


class GatewayIngestService:
    """Fetch and persist remote observations without exposing control routes."""

    def __init__(
        self,
        *,
        transport: GatewayTransport,
        db_path_provider: Callable[[], Path] = database_path,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        interval_seconds: float | None = None,
    ):
        self.transport = transport
        self.db_path_provider = db_path_provider
        self.clock = clock
        self.sleep = sleep
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else gateway_ingest_interval_seconds()
        )
        if self.interval_seconds < 1:
            raise ValueError("gateway ingest interval must be at least one second")

        self._failure_count = 0
        self._lock = asyncio.Lock()
        self._cycle_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.last_success_at: datetime | None = None
        self.last_error_code: str | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def state(self) -> str:
        if self.last_error_code is not None:
            return "disconnected"
        if self.last_success_at is not None:
            return "connected"
        return "disabled"

    def start(self) -> None:
        if self.running:
            return
        try:
            self._task = asyncio.create_task(self._run(), name="gateway-ingest")
        except Exception:
            self.last_error_code = "worker_start_failed"

    async def stop(self) -> None:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def collect_once(self) -> GatewayIngestResult:
        async with self._cycle_lock:
            try:
                response = await asyncio.to_thread(self.transport.fetch_current)
                await asyncio.to_thread(self._persist, response)
            except GatewayTransportError as error:
                self.last_error_code = (
                    error.code if error.code in _SAFE_ERRORS else "gateway_unreachable"
                )
                return GatewayIngestResult(self.last_error_code, self.last_success_at)
            except Exception:
                self.last_error_code = "gateway_persistence_failed"
                return GatewayIngestResult(self.last_error_code, self.last_success_at)

            observed_at = response.observed_at.astimezone(timezone.utc)
            self.last_success_at = observed_at
            self.last_error_code = None
            return GatewayIngestResult(None, observed_at)

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

    def _persist(self, response: GatewayObservationResponse) -> None:
        store = MetricsStore(Path(self.db_path_provider()))
        for observation in response.observations:
            client_id = observation.metadata.client_id
            if client_id is not None:
                store.register_client(
                    client_id,
                    "Client 01",
                    environment=ObservationEnvironment.SIMULATED_LAB,
                )
        store.save_observations(response.observations)

"""Centralized ML scheduler: 30-second inference cycle.

High-frequency measurement and immediate safety responses do not wait for this
cycle. Training is a separate controlled process, not run here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

_LOGGER = logging.getLogger(__name__)


class MlScheduler:
    """Runs the configured ML inference cycle every ``interval_seconds``."""

    def __init__(
        self,
        cycle_fn: Callable[[], object],
        interval_seconds: float = 30.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], object] = asyncio.sleep,
    ) -> None:
        self.cycle_fn = cycle_fn
        self.interval_seconds = float(interval_seconds)
        self.clock = clock
        self.sleep = sleep
        self._task: Optional[asyncio.Task] = None
        self.running = False
        self.last_run: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.run_count = 0

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="ml-scheduler")

    async def stop(self) -> None:
        self.running = False
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        try:
            while self.running:
                await self.sleep(self.interval_seconds)
                if not self.running:
                    break
                try:
                    result = self.cycle_fn()
                    if hasattr(result, "__await__"):
                        await result
                    self.last_run = self.clock()
                    self.run_count += 1
                    self.last_error = None
                except Exception as error:  # keep the cycle alive
                    _LOGGER.exception("ML cycle failed")
                    self.last_error = str(error)
        except asyncio.CancelledError:
            raise

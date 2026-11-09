"""Locked-down ICMP probe worker for configured Linux lab clients."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import platform
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Mapping, Sequence

from backend.app.services.lab_accounting_service import (
    LabAccountingService,
    lab_accounting_service,
)


_LOGGER = logging.getLogger(__name__)
_HELPER_PATH = "/usr/local/libexec/eb/eb-priv"
_SUDO_PATH = "/usr/bin/sudo"
_MAX_BACKOFF_SECONDS = 30.0
_MAX_OUTPUT_CHARS = 256
_RESULT_PATTERN = re.compile(
    r"ok 5 ([0-5]) ([0-9]+(?:\.[0-9]+)?) ([0-9]+(?:\.[0-9]+)?)\Z"
)
_FAILURE_CODES = {
    "no_namespace",
    "timeout",
    "no_reply",
    "parse_error",
    "helper_missing",
    "probe_timeout",
    "probe_failed",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def probe_interval_seconds(environ: Mapping[str, str] | None = None) -> float:
    values = os.environ if environ is None else environ
    raw = values.get("EB_PROBE_INTERVAL", "").strip()
    try:
        interval = float(raw) if raw else 5.0
    except ValueError:
        interval = 5.0
    if not math.isfinite(interval):
        interval = 5.0
    return max(2.0, interval)


def parse_probe_output(output: str | bytes) -> tuple[int, int, float, float] | str:
    """Parse exactly one bounded helper result line, returning safe values/code."""

    if isinstance(output, bytes):
        try:
            output = output.decode("ascii")
        except UnicodeDecodeError:
            return "parse_error"
    if not isinstance(output, str) or len(output) > _MAX_OUTPUT_CHARS:
        return "parse_error"
    if output.endswith("\n"):
        output = output[:-1]
    if "\n" in output or "\r" in output:
        return "parse_error"

    failure = re.fullmatch(
        r"fail (no_namespace|timeout|no_reply|parse_error)", output
    )
    if failure:
        return failure.group(1)

    match = _RESULT_PATTERN.fullmatch(output)
    if match is None:
        return "parse_error"
    received = int(match.group(1))
    average = float(match.group(2))
    variation = float(match.group(3))
    if (
        not math.isfinite(average)
        or not math.isfinite(variation)
        or average < 0
        or variation < 0
        or received < 1
    ):
        return "parse_error"
    return 5, received, average, variation


@dataclass(frozen=True)
class _ProbeSample:
    observed_at: datetime
    sent: int | None
    received: int | None
    average_ms: float | None
    variation_ms: float | None
    error_code: str | None


Runner = Callable[..., subprocess.CompletedProcess]


class LatencyProbeService:
    """Probe configured slots sequentially and expose only safe metric values."""

    def __init__(
        self,
        *,
        accounting: LabAccountingService = lab_accounting_service,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        runner: Runner = subprocess.run,
        platform_name: str | None = None,
        interval_seconds: float | None = None,
        helper_path: str = _HELPER_PATH,
    ):
        self.accounting = accounting
        self.clock = clock
        self.sleep = sleep
        self.runner = runner
        self.platform = platform_name or platform.system().lower()
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else probe_interval_seconds()
        )
        if self.interval_seconds < 2:
            raise ValueError("probe interval must be at least two seconds")
        self.helper_path = helper_path
        self.enabled = False
        self.last_success_at: datetime | None = None
        self.last_error_code: str | None = None
        self._state = "helper_missing" if self.platform == "linux" else "disabled"
        self._samples: dict[int, _ProbeSample] = {}
        self._samples_lock = threading.RLock()
        self._cycle_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._failure_count = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Enable only on Linux when the restricted helper can be executed."""

        if self.running:
            return
        setting = os.environ.get("EB_LATENCY_PROBE", "").strip()
        if self.platform != "linux" or setting == "0":
            self.enabled = False
            self._state = "disabled"
            self.last_error_code = None
            return

        try:
            helper_available = self._check_helper()
        except Exception:
            _LOGGER.exception("latency probe helper availability check failed")
            helper_available = False

        if not helper_available:
            self.enabled = False
            self._state = "helper_missing"
            self.last_error_code = "helper_missing"
            return

        self.enabled = True
        self.last_error_code = None
        self._state = "running"
        try:
            self._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="latency-probe",
            )
            self._task = asyncio.create_task(
                self._run(),
                name="latency-probe",
            )
        except Exception:
            self.enabled = False
            self._state = "failing"
            self.last_error_code = "probe_failed"
            _LOGGER.exception("latency probe worker could not start")

    async def stop(self) -> None:
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
        if self.enabled:
            self.enabled = False
            self._state = "disabled"

    async def probe_once(self) -> None:
        """Probe all currently configured lab slots serially."""

        async with self._cycle_lock:
            loop = asyncio.get_running_loop()
            executor = self._executor
            if executor is None:
                executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="latency-probe-test",
                )
                temporary_executor = True
            else:
                temporary_executor = False
            cycle = loop.run_in_executor(executor, self._probe_all)
            try:
                await asyncio.shield(cycle)
            except asyncio.CancelledError:
                await asyncio.shield(cycle)
                raise
            finally:
                if temporary_executor:
                    executor.shutdown(wait=True, cancel_futures=True)

    async def _run(self) -> None:
        try:
            while True:
                await self.probe_once()
                if self.last_error_code is None:
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
            self.last_error_code = "probe_failed"
            self._state = "failing"
            _LOGGER.exception("latency probe polling loop failed")

    def _check_helper(self) -> bool:
        command = [
            _SUDO_PATH,
            "-n",
            self.helper_path,
            "probe",
            "1",
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        result = parse_probe_output(completed.stdout or "")
        if isinstance(result, tuple):
            return completed.returncode == 0
        return (
            completed.returncode != 0
            and isinstance(result, str)
            and result
            in ("no_namespace", "timeout", "no_reply", "parse_error")
        )

    def _probe_all(self) -> None:
        first_error: str | None = None
        successes = 0
        try:
            inventory: Sequence = tuple(self.accounting.inventory)
        except Exception:
            _LOGGER.exception("latency probe inventory unavailable")
            self._record_global_failure("probe_failed")
            return

        for client in inventory:
            slot = client.client_number
            sample = self._probe_one(slot, self._now())
            with self._samples_lock:
                self._samples[slot] = sample
            if sample.error_code is None:
                successes += 1
                self.last_success_at = sample.observed_at
            elif first_error is None:
                first_error = sample.error_code

        if first_error is not None or not inventory:
            self.last_error_code = first_error or "probe_failed"
            self._state = "failing"
        elif successes == len(inventory):
            self.last_error_code = None
            self._state = "running"

    def _probe_one(self, slot: int, now: datetime) -> _ProbeSample:
        if isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= 9:
            return _ProbeSample(now, None, None, None, None, "no_namespace")
        command = [
            _SUDO_PATH,
            "-n",
            self.helper_path,
            "probe",
            str(slot),
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _ProbeSample(now, None, None, None, None, "probe_timeout")
        except Exception:
            _LOGGER.exception("latency probe subprocess failed")
            return _ProbeSample(now, None, None, None, None, "probe_failed")

        parsed = parse_probe_output(completed.stdout or "")
        if isinstance(parsed, str):
            code = parsed if parsed in _FAILURE_CODES else "parse_error"
            return _ProbeSample(now, None, None, None, None, code)
        sent, received, average, variation = parsed
        if completed.returncode != 0:
            return _ProbeSample(now, None, None, None, None, "probe_failed")
        return _ProbeSample(now, sent, received, average, variation, None)

    def metrics_for_slot(
        self,
        slot: int,
        now: datetime,
    ) -> dict[str, float] | None:
        """Return probe metrics only while the successful sample is <=15s old."""

        with self._samples_lock:
            sample = self._samples.get(slot)
        if sample is None or sample.error_code is not None:
            return None
        age = now.astimezone(timezone.utc) - sample.observed_at
        if age < timedelta(0) or age > timedelta(seconds=15):
            return None
        assert sample.sent is not None and sample.received is not None
        assert sample.average_ms is not None and sample.variation_ms is not None
        return {
            "rtt_ms": sample.average_ms,
            "rtt_variation_ms": sample.variation_ms,
            "packet_loss_percent": (sample.sent - sample.received)
            / sample.sent
            * 100,
        }

    def _record_global_failure(self, error_code: str) -> None:
        self.last_error_code = error_code
        self._state = "failing"
        with self._samples_lock:
            for slot in tuple(self._samples):
                self._samples[slot] = _ProbeSample(
                    self._now(), None, None, None, None, error_code
                )

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("probe clock must return an aware datetime")
        return now.astimezone(timezone.utc)


latency_probe_service = LatencyProbeService()

import asyncio
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.latency_probe_service import (
    LatencyProbeService,
    _ProbeSample,
    _PROBE_TIMEOUT_SECONDS,
    parse_probe_output,
)


NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)


def run_async(test):
    @wraps(test)
    def wrapper(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))

    return wrapper


class FakeAccounting:
    inventory = tuple(SimpleNamespace(client_number=slot) for slot in (1, 2, 3))


def completed(output, returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=output)


def test_probe_parser_accepts_only_one_fixed_format_line():
    assert parse_probe_output("ok 5 4 1.25 0.30\n") == (5, 4, 1.25, 0.3)
    for reason in ("no_namespace", "timeout", "no_reply", "parse_error"):
        assert parse_probe_output(f"fail {reason}") == reason
    for invalid in (
        "",
        "ok 5 5 1 0\nfail no_reply",
        "ok 5 5 1; rm -rf / 0",
        "ok 5 5 nan 0",
        "ok 5 0 1 0",
        "x" * 257,
    ):
        assert parse_probe_output(invalid) == "parse_error"


def test_probe_helper_missing_at_startup_does_not_raise(monkeypatch):
    monkeypatch.delenv("EB_LATENCY_PROBE", raising=False)

    def missing_helper(*_args, **_kwargs):
        raise FileNotFoundError("helper path")

    service = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=missing_helper,
        platform_name="linux",
    )

    service.start()

    assert service.enabled is False
    assert service.state == "helper_missing"
    assert service.last_error_code == "helper_missing"


@run_async
async def test_probe_default_enablement_requires_linux_and_available_helper(
    monkeypatch,
):
    monkeypatch.delenv("EB_LATENCY_PROBE", raising=False)
    calls = []

    def available_helper(argv, **_kwargs):
        calls.append(argv)
        return completed("ok 5 5 1.0 0.1\n")

    unsupported = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=available_helper,
        platform_name="windows",
    )
    unsupported.start()
    assert unsupported.enabled is False
    assert unsupported.state == "disabled"
    assert calls == []

    enabled = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=available_helper,
        platform_name="linux",
    )
    enabled.start()
    await asyncio.sleep(0.1)
    assert enabled.enabled is True
    assert enabled.state == "running"
    await enabled.stop()


@run_async
async def test_probe_cache_is_fresh_at_15_seconds_and_stale_afterward():
    service = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=lambda *_args, **_kwargs: completed("ok 5 4 12.5 0.8\n"),
        clock=lambda: NOW,
        platform_name="linux",
    )

    await service.probe_once()

    assert service.metrics_for_slot(1, NOW + timedelta(seconds=15)) == {
        "rtt_ms": 12.5,
        "rtt_variation_ms": 0.8,
        "packet_loss_percent": 20.0,
    }
    assert (
        service.metrics_for_slot(1, NOW + timedelta(seconds=15, milliseconds=1))
        is None
    )


@run_async
async def test_probes_run_concurrently_and_failed_result_replaces_cache():
    """Probes for multiple slots must run concurrently, not sequentially.

    The updated design runs one probe per slot in a thread pool so that a
    slow or unreachable client does not delay the others.  The maximum
    concurrency observed should therefore be > 1 when the inventory has
    multiple slots.
    """
    active = 0
    maximum_active = 0
    guard = threading.Lock()
    barrier = threading.Barrier(3)  # three slots in FakeAccounting

    def runner(*_args, **_kwargs):
        nonlocal active, maximum_active
        with guard:
            active += 1
            maximum_active = max(maximum_active, active)
        # Wait until all three probes are in flight before any returns.
        barrier.wait(timeout=2)
        with guard:
            active -= 1
        return completed("fail no_reply\n", returncode=1)

    service = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=runner,
        clock=lambda: NOW,
        platform_name="linux",
    )
    service._samples[1] = _ProbeSample(NOW, 5, 5, 1.0, 0.1, None)

    await service.probe_once()

    # All three probes must have run concurrently.
    assert maximum_active == 3
    assert service.metrics_for_slot(1, NOW) is None
    assert service.last_error_code == "no_reply"
    assert service.state == "failing"


@run_async
async def test_probe_worker_backoff_and_shutdown(monkeypatch):
    monkeypatch.delenv("EB_LATENCY_PROBE", raising=False)
    delays = []
    runner_calls = 0

    def runner(*_args, **_kwargs):
        nonlocal runner_calls
        runner_calls += 1
        if runner_calls == 1:
            return completed("ok 5 5 1.0 0.1\n")
        return completed("fail no_reply\n", returncode=1)

    service = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=runner,
        clock=lambda: NOW,
        sleep=lambda delay: _record_and_cancel(delay, delays),
        platform_name="linux",
        interval_seconds=5,
    )
    service.start()
    # Allow the async startup coroutine (_async_start) to run to completion
    # before we assert that the probe task has been created.
    await asyncio.sleep(0.1)
    assert service._task is not None
    with pytest.raises(asyncio.CancelledError):
        await service._task
    await service.stop()

    assert delays == [5, 10, 20, 30]
    assert service.running is False
    assert service.state == "disabled"


async def _record_and_cancel(delay, delays):
    delays.append(delay)
    if len(delays) == 4:
        raise asyncio.CancelledError


def test_interval_is_at_least_two_seconds():
    with pytest.raises(ValueError):
        LatencyProbeService(
            accounting=FakeAccounting(),
            platform_name="linux",
            interval_seconds=1,
        )


def test_probe_commands_use_fixed_helper_and_validated_slot():
    commands = []

    def runner(argv, **kwargs):
        commands.append((argv, kwargs))
        return completed("ok 5 5 1.0 0.1\n")

    service = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=runner,
        platform_name="linux",
    )
    assert service._probe_one(3, NOW).error_code is None
    assert commands[0][0] == [
        "/usr/bin/sudo",
        "-n",
        "/usr/local/libexec/eb/eb-priv",
        "probe",
        "3",
    ]
    assert commands[0][1]["timeout"] == _PROBE_TIMEOUT_SECONDS
    assert "shell" not in commands[0][1]


def test_helper_scripts_parse_and_reject_bad_inputs_without_execution():
    root = Path(__file__).resolve().parents[2]
    scripts = (
        root / "scripts/privileged/eb-priv",
        root / "scripts/privileged/install_eb_priv.sh",
        root / "scripts/privileged/uninstall_eb_priv.sh",
    )
    for script in scripts:
        checked = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, checked.stderr

    helper = scripts[0]
    bad_arguments = (
        (),
        ("unexpected",),
        ("probe",),
        ("probe", "0"),
        ("probe", "10"),
        ("probe", "1;ls"),
        ("probe", "1", "extra"),
    )
    for arguments in bad_arguments:
        result = subprocess.run(
            ["bash", str(helper), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert result.stdout == "fail parse_error\n"
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# Regression: slow / failing probes must not block GET endpoints or each other
# ---------------------------------------------------------------------------

@run_async
async def test_slow_probe_does_not_delay_others_past_timeout():
    """A probe that takes longer than probe_timeout_seconds must not delay
    the other slots by more than the hard timeout.

    Each probe sleeps for SLOW_PROBE_MS.  With concurrent execution the total
    wall-clock time for all three slots should be close to one slot's time,
    not three times that.
    """
    import time as _time

    SLOW_PROBE_MS = 0.3  # 300 ms per probe
    HARD_TIMEOUT = 1.0   # per-client timeout passed to LatencyProbeService

    def slow_runner(*_args, **_kwargs):
        _time.sleep(SLOW_PROBE_MS)
        return completed("ok 5 5 1.0 0.1\n")

    service = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=slow_runner,
        clock=lambda: NOW,
        platform_name="linux",
        probe_timeout_seconds=HARD_TIMEOUT,
    )

    t0 = _time.monotonic()
    await service.probe_once()
    elapsed = _time.monotonic() - t0

    # With 3 concurrent probes each taking SLOW_PROBE_MS, the cycle should
    # finish in < 2 × SLOW_PROBE_MS, not 3 × SLOW_PROBE_MS.
    assert elapsed < SLOW_PROBE_MS * 2, (
        f"probe cycle took {elapsed:.3f}s — slots are not running concurrently"
    )
    assert service.last_error_code is None
    assert service.state == "running"


@run_async
async def test_failing_probe_for_one_slot_does_not_exceed_hard_timeout():
    """A single failing / timing-out probe must not block others past the
    hard per-probe timeout, and must not prevent the good probes from recording
    their results.
    """
    import time as _time

    HARD_TIMEOUT = 0.5  # seconds

    def flaky_runner(argv, **_kwargs):
        slot = int(argv[-1])
        if slot == 2:
            # This slot exceeds the subprocess timeout; subprocess.run raises
            # TimeoutExpired which _probe_one converts to "probe_timeout".
            raise subprocess.TimeoutExpired(cmd=argv, timeout=HARD_TIMEOUT)
        return completed("ok 5 5 1.0 0.1\n")

    service = LatencyProbeService(
        accounting=FakeAccounting(),
        runner=flaky_runner,
        clock=lambda: NOW,
        platform_name="linux",
        probe_timeout_seconds=HARD_TIMEOUT,
    )

    t0 = _time.monotonic()
    await service.probe_once()
    elapsed = _time.monotonic() - t0

    # The whole cycle must finish within a small multiple of the timeout, not
    # N_slots × timeout.
    assert elapsed < HARD_TIMEOUT * 2.5, (
        f"probe cycle took {elapsed:.3f}s — failing slot is blocking others"
    )
    # Slots 1 and 3 should have good samples; slot 2 should have an error.
    assert service.metrics_for_slot(1, NOW) is not None
    assert service.metrics_for_slot(3, NOW) is not None
    assert service._samples[2].error_code == "probe_timeout"

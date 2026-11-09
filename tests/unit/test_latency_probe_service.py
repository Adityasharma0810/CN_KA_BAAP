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
    await asyncio.sleep(0)
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
async def test_probes_run_sequentially_and_failed_result_replaces_cache():
    active = 0
    maximum_active = 0
    guard = threading.Lock()
    def runner(*_args, **_kwargs):
        nonlocal active, maximum_active
        with guard:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.005)
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

    assert maximum_active == 1
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
    assert commands[0][1]["timeout"] == 6
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

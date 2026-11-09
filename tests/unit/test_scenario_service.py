import asyncio
import json
import subprocess
from datetime import datetime, timedelta, timezone
from functools import wraps
from types import SimpleNamespace

import pytest

import backend.app.services.scenario_service as scenario_module
from backend.app.models.scenario_schemas import ScenarioStartRequest
from backend.app.services.scenario_service import (
    ScenarioService,
    ScenarioServiceError,
)


NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def run_async(test):
    @wraps(test)
    def wrapper(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))

    return wrapper


class FakeAccounting:
    inventory = tuple(
        SimpleNamespace(client_number=slot, client_id=f"client-{slot:08d}")
        for slot in range(1, 6)
    )


def completed(stdout, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def runner_for(calls):
    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        arguments = argv[3:]
        if arguments[:2] == ["traffic", "start"]:
            return completed(f"ok traffic_started {arguments[2]}\n")
        if arguments[:2] == ["traffic", "stop"]:
            return completed(f"ok traffic_stopped {arguments[2]}\n")
        if arguments == ["traffic", "stop-all"]:
            return completed("ok traffic_stopped_all\n")
        if arguments == ["bottleneck", "off"]:
            return completed("ok bottleneck_off\n")
        if arguments[:1] == ["bottleneck"]:
            return completed(f"ok bottleneck {arguments[1]}\n")
        raise AssertionError(f"unexpected helper argv: {argv}")

    return runner


def stub_observations(monkeypatch):
    monkeypatch.setattr(
        scenario_module,
        "build_historical_observations",
        lambda **_kwargs: SimpleNamespace(observations=[]),
    )
    monkeypatch.setattr(scenario_module, "_tool_version", lambda *_args: "test")


@run_async
async def test_start_exclusivity_stop_cleanup_and_manifest(tmp_path, monkeypatch):
    stub_observations(monkeypatch)
    calls = []

    async def pause(_seconds):
        await asyncio.Event().wait()

    service = ScenarioService(
        runner=runner_for(calls),
        clock=lambda: NOW,
        sleep=pause,
        run_dir=tmp_path,
        accounting=FakeAccounting(),
    )

    started = await service.start("call_vs_download", duration_seconds=10, seed=7)
    assert started.state == "running"
    assert started.scenario_id == "call_vs_download"
    assert [call[0][3:] for call in calls] == [
        ["traffic", "start", "1", "call", "10"],
        ["traffic", "start", "2", "bulk", "10"],
    ]
    assert all(call[1]["timeout"] == 5.0 for call in calls)
    with pytest.raises(ScenarioServiceError, match="scenario_already_running"):
        await service.start("wan_drop")

    stopped = await service.stop()

    assert stopped.state == "stopped"
    assert [call[0][3:] for call in calls[-2:]] == [
        ["traffic", "stop-all"],
        ["bottleneck", "off"],
    ]
    manifest_path = tmp_path / started.run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["seed"] == 7
    assert manifest["slot_to_profile"] == {"1": "call", "2": "bulk"}
    assert manifest["outcome"]["status"] == "stopped"
    assert (manifest_path.parent / "observations.csv").is_file()


@run_async
async def test_wan_drop_timeline_auto_stops_and_records_mapping(tmp_path, monkeypatch):
    stub_observations(monkeypatch)
    calls = []
    current_time = [NOW]

    async def advance(seconds):
        current_time[0] += timedelta(seconds=seconds)

    service = ScenarioService(
        runner=runner_for(calls),
        clock=lambda: current_time[0],
        sleep=advance,
        run_dir=tmp_path,
        accounting=FakeAccounting(),
    )

    started = await service.start("wan_drop", duration_seconds=10)
    await service._run.task

    assert started.phases[0].at_seconds == 5
    assert [call[0][3:] for call in calls] == [
        ["bottleneck", "100"],
        ["traffic", "start", "1", "stream", "10"],
        ["traffic", "start", "2", "call", "10"],
        ["bottleneck", "20"],
        ["bottleneck", "100"],
        ["traffic", "stop-all"],
        ["bottleneck", "off"],
    ]
    manifest = json.loads(
        (tmp_path / started.run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["outcome"]["status"] == "completed"
    assert manifest["lab_client_count"] == 5


@run_async
async def test_missing_helper_is_safe_and_cleanup_is_attempted(tmp_path, monkeypatch):
    stub_observations(monkeypatch)
    calls = []

    def missing(argv, **_kwargs):
        calls.append(argv)
        raise FileNotFoundError("/private/helper/path")

    service = ScenarioService(
        runner=missing,
        clock=lambda: NOW,
        run_dir=tmp_path,
        accounting=FakeAccounting(),
    )
    with pytest.raises(ScenarioServiceError) as error:
        await service.start("call_vs_download")

    assert error.value.code == "helper_missing"
    assert len(calls) == 3
    assert service.status().error_code == "helper_missing"
    assert service.status().install_command == "sudo bash scripts/privileged/install_eb_priv.sh"


def test_scenario_request_is_bounded_and_forbids_extra_fields():
    assert ScenarioStartRequest(duration_seconds=120, seed=3).duration_seconds == 120
    with pytest.raises(ValueError):
        ScenarioStartRequest(duration_seconds=121)
    with pytest.raises(ValueError):
        ScenarioStartRequest(unbounded=True)


def test_tvs_mapping_uses_fewer_streams_for_three_client_lab():
    service = ScenarioService(accounting=FakeAccounting())

    assert service._profile_mapping("tvs_and_gamer", 3) == {
        1: "stream",
        2: "stream",
        3: "game",
    }
    assert service._profile_mapping("tvs_and_gamer", 5) == {
        1: "stream",
        2: "stream",
        3: "stream",
        5: "game",
    }

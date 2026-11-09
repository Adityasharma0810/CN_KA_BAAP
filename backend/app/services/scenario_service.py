"""Bounded Scenario Lab runner using only the installed eb-priv helper."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import os
import platform
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Sequence

from backend.app.models.scenario_schemas import (
    ScenarioDefinition,
    ScenarioPhase,
    ScenarioStatusResponse,
)
from backend.app.services.lab_accounting_service import lab_accounting_service
from backend.app.services.observation_query_service import (
    ObservationQueryError,
    build_historical_observations,
)


_LOGGER = logging.getLogger(__name__)
_HELPER = "/usr/local/libexec/eb/eb-priv"
_SUDO = "/usr/bin/sudo"
_INSTALL_COMMAND = "sudo bash scripts/privileged/install_eb_priv.sh"
_SUCCESS_OUTPUT = re.compile(
    r"ok (?:traffic_(?:started|stopped) [1-9][0-9]?|traffic_stopped_all|"
    r"bottleneck (?:100|50|20|10|5)|bottleneck_off)\Z"
)
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_run_dir() -> Path:
    configured = os.environ.get("EB_SCENARIO_RUN_DIR", "").strip()
    return Path(configured) if configured else Path(__file__).resolve().parents[3] / "data/scenario_runs"


def _tool_version(path: str, argument: str, pattern: str) -> str:
    if not Path(path).is_file():
        return "unavailable"
    try:
        result = subprocess.run(
            [path, argument],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    text = (result.stdout + result.stderr)[:512]
    match = re.search(pattern, text)
    return match.group(1) if match else "unavailable"


CATALOG: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        id="call_vs_download",
        name="Call vs download",
        description="A low-rate call flow competes with a bulk TCP download.",
        duration_seconds=30,
        slots_needed=2,
    ),
    ScenarioDefinition(
        id="wan_drop",
        name="WAN capacity drop",
        description="Stream and call traffic run while the shared bottleneck changes from 100 to 20 Mbit/s and back.",
        duration_seconds=60,
        slots_needed=2,
    ),
    ScenarioDefinition(
        id="tvs_and_gamer",
        name="TVs and gamer",
        description=(
            "Runs up to three stream flows plus one game flow. A 3-client lab "
            "uses two streams and one game flow; the full 3 TVs + gamer mapping "
            "uses slots 1-3 and 5 (slot 4 is reserved) and needs five lab clients: "
            "sudo EB_LAB_CLIENTS=5 bash scripts/setup_gateway.sh"
        ),
        duration_seconds=60,
        slots_needed=3,
    ),
)


class ScenarioServiceError(RuntimeError):
    def __init__(self, code: str, *, status_code: int = 503):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass
class _Run:
    run_id: str
    scenario_id: str
    seed: int | None
    duration_seconds: int
    started_at: datetime
    ends_at: datetime
    profiles: dict[int, str]
    phases: list[ScenarioPhase]
    state: str = "starting"
    error_code: str | None = None
    task: asyncio.Task | None = None
    manifest_path: Path | None = None
    stop_requested: bool = False
    manifest: dict = field(default_factory=dict)


Runner = Callable[..., subprocess.CompletedProcess]


class ScenarioService:
    """Owns the single active run and guarantees bounded cleanup."""

    def __init__(
        self,
        *,
        runner: Runner = subprocess.run,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        run_dir: Path | None = None,
        accounting=lab_accounting_service,
        helper_path: str = _HELPER,
    ):
        self.runner = runner
        self.clock = clock
        self.sleep = sleep
        self.run_dir = run_dir or _default_run_dir()
        self.accounting = accounting
        self.helper_path = helper_path
        self._lock = asyncio.Lock()
        self._run: _Run | None = None
        self._last_status = ScenarioStatusResponse(state="idle")

    def _now(self) -> datetime:
        current = self.clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("scenario clock must return an aware datetime")
        return current.astimezone(timezone.utc)

    def _slot_count(self) -> int:
        return len(self.accounting.inventory)

    def _profile_mapping(self, scenario_id: str, slot_count: int) -> dict[int, str]:
        if scenario_id == "call_vs_download":
            if slot_count < 2:
                raise ScenarioServiceError("insufficient_lab_clients", status_code=409)
            return {1: "call", 2: "bulk"}
        if scenario_id == "wan_drop":
            if slot_count < 2:
                raise ScenarioServiceError("insufficient_lab_clients", status_code=409)
            return {1: "stream", 2: "call"}
        if scenario_id == "tvs_and_gamer":
            if slot_count < 3:
                raise ScenarioServiceError("insufficient_lab_clients", status_code=409)
            if slot_count >= 5:
                return {1: "stream", 2: "stream", 3: "stream", 5: "game"}
            game_slot = slot_count
            return {1: "stream", 2: "stream", game_slot: "game"}
        raise ScenarioServiceError("unknown_scenario", status_code=404)

    def _phases(self, scenario_id: str, duration: int) -> list[ScenarioPhase]:
        if scenario_id != "wan_drop":
            return []
        return [
            ScenarioPhase(name="capacity_reduced", at_seconds=duration // 2, action="bottleneck 20"),
            ScenarioPhase(name="capacity_restored", at_seconds=(duration * 4) // 5, action="bottleneck 100"),
        ]

    def _status(self, run: _Run | None = None) -> ScenarioStatusResponse:
        current = run or self._run
        if current is None:
            return self._last_status
        now = self._now()
        return ScenarioStatusResponse(
            state=current.state,
            run_id=current.run_id,
            scenario_id=current.scenario_id,
            started_at=current.started_at,
            ends_at=current.ends_at,
            remaining_seconds=max(0, math.ceil((current.ends_at - now).total_seconds())),
            phases=current.phases,
            manifest_id=current.run_id,
            error_code=current.error_code,
            install_command=_INSTALL_COMMAND if current.error_code == "helper_missing" else None,
        )

    def catalogue(self) -> list[ScenarioDefinition]:
        return list(CATALOG)

    def status(self) -> ScenarioStatusResponse:
        return self._status()

    @property
    def active_profiles(self) -> dict[int, str]:
        run = self._run
        if run is None or run.state not in {"starting", "running", "stopping"}:
            return {}
        return dict(run.profiles)

    @property
    def active_started_at(self) -> datetime | None:
        run = self._run
        if run is None or run.state not in {"starting", "running", "stopping"}:
            return None
        return run.started_at

    async def start(
        self,
        scenario_id: str,
        *,
        duration_seconds: int | None = None,
        seed: int | None = None,
    ) -> ScenarioStatusResponse:
        async with self._lock:
            if self._run is not None and self._run.state in {"starting", "running", "stopping"}:
                raise ScenarioServiceError("scenario_already_running", status_code=409)
            definition = next((item for item in CATALOG if item.id == scenario_id), None)
            if definition is None:
                raise ScenarioServiceError("unknown_scenario", status_code=404)
            duration = (
                definition.duration_seconds
                if duration_seconds is None
                else duration_seconds
            )
            if (
                not isinstance(duration, int)
                or isinstance(duration, bool)
                or not 5 <= duration <= 120
            ):
                raise ScenarioServiceError("invalid_duration", status_code=422)
            profiles = self._profile_mapping(scenario_id, self._slot_count())
            now = self._now()
            run = _Run(
                run_id=uuid.uuid4().hex,
                scenario_id=scenario_id,
                seed=seed,
                duration_seconds=duration,
                started_at=now,
                ends_at=now + timedelta(seconds=duration),
                profiles=profiles,
                phases=self._phases(scenario_id, duration),
                manifest_path=None,
            )
            run.manifest_path = self.run_dir / run.run_id / "manifest.json"
            try:
                run.manifest = self._make_manifest(run)
                self._write_manifest(run)
            except OSError as error:
                raise ScenarioServiceError(
                    "scenario_storage_failed",
                    status_code=503,
                ) from error
            self._run = run
            try:
                if scenario_id == "wan_drop":
                    await self._invoke(["bottleneck", "100"])
                for slot, profile in profiles.items():
                    await self._invoke(
                        ["traffic", "start", str(slot), profile, str(duration)]
                    )
                self._write_manifest(run)
            except ScenarioServiceError as error:
                run.state = "error"
                run.error_code = error.code
                await self._cleanup(run, "error")
                self._run = None
                self._last_status = self._status(run)
                raise
            except OSError as error:
                run.state = "error"
                run.error_code = "scenario_storage_failed"
                await self._cleanup(run, "error")
                self._run = None
                self._last_status = self._status(run)
                raise ScenarioServiceError(
                    "scenario_storage_failed",
                    status_code=503,
                ) from error
            run.state = "running"
            run.task = asyncio.create_task(self._run_timeline(run), name=f"scenario-{run.run_id}")
            return self._status(run)

    async def _invoke(self, arguments: Sequence[str]) -> str:
        argv = [_SUDO, "-n", self.helper_path, *arguments]
        try:
            result = await asyncio.to_thread(
                self.runner,
                argv,
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError) as error:
            _LOGGER.warning("scenario helper call failed (%s)", type(error).__name__)
            raise ScenarioServiceError("helper_missing") from error
        output = result.stdout
        if not isinstance(output, str) or len(output) > 160 or "\n" in output.rstrip("\n") or "\r" in output:
            raise ScenarioServiceError("helper_missing")
        line = output[:-1] if output.endswith("\n") else output
        if result.returncode == 0 and _SUCCESS_OUTPUT.fullmatch(line):
            return line
        raise ScenarioServiceError("helper_missing")

    def _make_manifest(self, run: _Run) -> dict:
        return {
            "run_id": run.run_id,
            "scenario_id": run.scenario_id,
            "seed": run.seed,
            "start_utc": run.started_at.isoformat(),
            "end_utc": None,
            "planned_timeline": [
                {"phase": "start", "at_seconds": 0, "action": "start declared traffic"},
                *[
                    {"phase": phase.name, "at_seconds": phase.at_seconds, "action": phase.action}
                    for phase in run.phases
                ],
                {"phase": "stop", "at_seconds": run.duration_seconds, "action": "stop all traffic and restore bottleneck"},
            ],
            "slot_to_profile": {str(slot): profile for slot, profile in run.profiles.items()},
            "tool_versions": {
                "iperf3": _tool_version("/usr/bin/iperf3", "--version", r"iperf ([0-9]+(?:\.[0-9]+)+)"),
                "ping": _tool_version("/usr/bin/ping", "-V", r"iputils ([0-9]+)"),
                "kernel": platform.release(),
                "python": platform.python_version(),
            },
            "lab_client_count": self._slot_count(),
            "outcome": {"status": "running", "safe_code": None},
        }

    def _write_manifest(self, run: _Run) -> None:
        assert run.manifest_path is not None
        run.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = run.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(run.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(run.manifest_path)

    async def _run_timeline(self, run: _Run) -> None:
        outcome = "completed"
        try:
            elapsed = 0
            for phase in run.phases:
                wait_seconds = max(0, phase.at_seconds - elapsed)
                if wait_seconds:
                    await self.sleep(wait_seconds)
                await self._invoke(["bottleneck", phase.action.rsplit(" ", 1)[1]])
                elapsed = phase.at_seconds
            remaining = max(0.0, (run.ends_at - self._now()).total_seconds())
            if remaining:
                await self.sleep(remaining)
        except asyncio.CancelledError:
            outcome = "stopped" if run.stop_requested else "error"
            if outcome == "error":
                run.error_code = "scenario_cancelled"
            raise
        except ScenarioServiceError as error:
            run.error_code = error.code
            outcome = "error"
        except Exception:
            _LOGGER.exception("scenario runner failed")
            run.error_code = "scenario_failed"
            outcome = "error"
        finally:
            await self._cleanup(run, outcome)

    async def _cleanup(self, run: _Run, outcome: str) -> None:
        run.state = "stopping"
        cleanup_failed = False
        for arguments in (["traffic", "stop-all"], ["bottleneck", "off"]):
            try:
                await self._invoke(arguments)
            except ScenarioServiceError:
                cleanup_failed = True
        ended_at = self._now()
        if cleanup_failed:
            outcome = "error"
            run.error_code = run.error_code or "cleanup_failed"
        run.manifest["end_utc"] = ended_at.isoformat()
        run.manifest["outcome"] = {
            "status": outcome,
            "safe_code": run.error_code if outcome == "error" else None,
        }
        try:
            self._export_observations(run, ended_at)
            self._write_manifest(run)
        except (OSError, ObservationQueryError, ValueError):
            _LOGGER.exception("scenario evidence export failed")
            run.error_code = "observations_export_failed"
            outcome = "error"
            run.manifest["outcome"] = {"status": "error", "safe_code": run.error_code}
            try:
                self._write_manifest(run)
            except OSError:
                _LOGGER.exception("scenario manifest update failed")
        run.state = outcome
        self._last_status = self._status(run)
        if self._run is run:
            self._run = None

    def _export_observations(self, run: _Run, ended_at: datetime) -> None:
        assert run.manifest_path is not None
        output = run.manifest_path.parent / "observations.csv"
        rows: list[dict] = []
        for scope, source in (
            ("client", "linux_namespace_lab"),
            ("aggregate_gateway", "linux_gateway"),
        ):
            history = build_historical_observations(
                source=source,
                scope=scope,
                start=run.started_at,
                end=ended_at,
                limit=1000,
                order="oldest",
            )
            for item in history.observations:
                observation = item.observation
                rows.append(
                    {
                        "observed_at": observation.metadata.observed_at.isoformat(),
                        "scope": observation.metadata.scope,
                        "client_id": observation.metadata.client_id or "",
                        "download_mbps": observation.download_mbps,
                        "upload_mbps": observation.upload_mbps,
                        "rtt_ms": observation.rtt_ms,
                        "rtt_variation_ms": observation.rtt_variation_ms,
                        "packet_loss_percent": observation.packet_loss_percent,
                    }
                )
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    "observed_at",
                    "scope",
                    "client_id",
                    "download_mbps",
                    "upload_mbps",
                    "rtt_ms",
                    "rtt_variation_ms",
                    "packet_loss_percent",
                ),
            )
            writer.writeheader()
            writer.writerows(rows)

    async def stop(self) -> ScenarioStatusResponse:
        run = self._run
        if run is None:
            return self._status()
        run.stop_requested = True
        run.state = "stopping"
        task = run.task
        if task is None:
            await self._cleanup(run, "stopped")
        else:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if self._run is run:
                await self._cleanup(run, "stopped")
        return self._status()

    async def shutdown(self) -> None:
        await self.stop()


scenario_service = ScenarioService()

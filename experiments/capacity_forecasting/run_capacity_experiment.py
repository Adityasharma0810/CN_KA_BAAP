#!/usr/bin/env python3
"""Run controlled lab traffic and collect verified bottleneck-capacity telemetry."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TextIO

from experiments.capacity_forecasting.collect_gateway_telemetry import (
    BRIDGE_NAME,
    CLIENT_NAMES,
    parse_tbf_capacity,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BOTTLENECK_SCRIPT = REPOSITORY_ROOT / "scripts" / "set_bottleneck.sh"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "data" / "capacity_forecasting" / "raw"
DEFAULT_SAMPLE_INTERVAL = 1.0
DEFAULT_DURATION = 60.0
EXISTING_SERVER_PORTS = (5201, 5202)
MANAGED_SERVER_PORTS = tuple(range(5203, 5224))
TRAFFIC_PROFILE = "three-client-reverse-tcp-iperf3"


class ExperimentError(RuntimeError):
    """A prerequisite, safety check, or run operation failed."""


@dataclass(frozen=True)
class CapacityEvent:
    offset_s: float
    capacity_mbps: int


def scenario_schedule(scenario: str, duration: float) -> tuple[CapacityEvent, ...]:
    """Return a deterministic capacity schedule clipped to the run duration."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be positive and finite")
    if scenario == "constant":
        return (CapacityEvent(0.0, 100),)
    if scenario == "step":
        schedule = (
            CapacityEvent(0.0, 100),
            CapacityEvent(20.0, 40),
            CapacityEvent(40.0, 100),
        )
    elif scenario == "periodic":
        schedule = tuple(
            CapacityEvent(float(offset), 80 if index % 2 == 0 else 120)
            for index, offset in enumerate(range(0, math.ceil(duration), 10))
            if offset < duration
        )
    else:
        raise ValueError(f"unsupported scenario: {scenario}")
    return tuple(event for event in schedule if event.offset_s < duration)


def _read_root_qdisc(
    runner: Callable = subprocess.run,
) -> tuple[dict[str, object], str]:
    """Inspect and return the sole root qdisc and exact tc JSON output."""
    try:
        result = runner(
            ["tc", "-j", "-d", "qdisc", "show", "dev", BRIDGE_NAME],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ExperimentError(f"could not inspect {BRIDGE_NAME} root qdisc: {error}") from error
    if result.returncode != 0:
        raise ExperimentError(
            result.stderr.strip() or f"tc exited with status {result.returncode}"
        )
    try:
        qdiscs = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ExperimentError(f"tc returned malformed qdisc JSON: {error}") from error
    if not isinstance(qdiscs, list):
        raise ExperimentError("tc qdisc JSON must be a list")
    roots = [
        item
        for item in qdiscs
        if isinstance(item, dict) and item.get("root") is True
    ]
    if len(roots) != 1:
        raise ExperimentError(
            f"expected exactly one root qdisc on {BRIDGE_NAME}, found {len(roots)}"
        )
    return roots[0], result.stdout


class BottleneckManager:
    """Own only the root TBF installed through the existing script."""

    def __init__(
        self,
        *,
        command_runner: Callable = subprocess.run,
        qdisc_reader: Callable[[], tuple[dict[str, object], str]] | None = None,
        use_sudo: bool | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.qdisc_reader = qdisc_reader or (
            lambda: _read_root_qdisc(command_runner)
        )
        self.use_sudo = os.geteuid() != 0 if use_sudo is None else use_sudo
        self.expected_capacity_mbps: int | None = None
        self.snapshots: list[dict[str, object]] = []

    def _command(self, *args: str) -> list[str]:
        prefix = ["sudo", "-n"] if self.use_sudo else []
        return [*prefix, *args]

    def preflight(self) -> None:
        if self.use_sudo:
            result = self.command_runner(
                ["sudo", "-n", "true"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode != 0:
                raise ExperimentError(
                    "the set_bottleneck.sh workflow requires sudo; "
                    "non-interactive sudo authorization is unavailable"
                )
        root, raw = self.qdisc_reader()
        if root.get("kind") != "noqueue":
            raise ExperimentError(
                f"refusing to replace unexpected root qdisc {root.get('kind')!r}; "
                f"observed tc JSON: {raw.strip()}"
            )

    def set_capacity(self, capacity_mbps: int, *, initial: bool = False) -> str:
        if capacity_mbps <= 0:
            raise ValueError("capacity must be positive")
        root, raw = self.qdisc_reader()
        if initial:
            if root.get("kind") != "noqueue":
                raise ExperimentError(
                    f"refusing to replace unexpected root qdisc "
                    f"{root.get('kind')!r}: {raw.strip()}"
                )
        else:
            if self.expected_capacity_mbps is None or root.get("kind") != "tbf":
                raise ExperimentError(
                    "the active root qdisc is no longer the runner-owned TBF; "
                    "preserving current network state"
                )
            try:
                actual = parse_tbf_capacity(raw)
            except ValueError as error:
                raise ExperimentError(
                    f"could not verify runner-owned TBF before transition: {error}"
                ) from error
            if not math.isclose(actual, self.expected_capacity_mbps, abs_tol=1e-6):
                raise ExperimentError(
                    f"active TBF changed unexpectedly to {actual:g} Mbps; "
                    "preserving current network state"
                )

        result = self.command_runner(
            self._command("bash", str(BOTTLENECK_SCRIPT), str(capacity_mbps)),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if result.returncode != 0:
            raise ExperimentError(
                result.stderr.strip()
                or f"set_bottleneck.sh exited with status {result.returncode}"
            )
        self.expected_capacity_mbps = capacity_mbps
        root_after, raw_after = self.qdisc_reader()
        try:
            actual_after = parse_tbf_capacity(raw_after)
        except ValueError as error:
            raise ExperimentError(
                f"set_bottleneck.sh did not install a verifiable root TBF: {error}"
            ) from error
        if root_after.get("kind") != "tbf" or not math.isclose(
            actual_after, capacity_mbps, abs_tol=1e-6
        ):
            raise ExperimentError(
                f"requested {capacity_mbps} Mbps, but active root TBF reports "
                f"{actual_after:g} Mbps"
            )
        self.snapshots.append(
            {
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "requested_capacity_mbps": capacity_mbps,
                "tc_json": json.loads(raw_after),
            }
        )
        return raw_after

    def cleanup(self) -> None:
        if self.expected_capacity_mbps is None:
            return
        root, raw = self.qdisc_reader()
        if root.get("kind") != "tbf":
            raise ExperimentError(
                "refusing to remove qdisc: active root is not the runner-owned TBF"
            )
        try:
            actual = parse_tbf_capacity(raw)
        except ValueError as error:
            raise ExperimentError(
                f"refusing to remove unverified root qdisc: {error}"
            ) from error
        if not math.isclose(actual, self.expected_capacity_mbps, abs_tol=1e-6):
            raise ExperimentError(
                f"refusing to remove qdisc: expected runner TBF "
                f"{self.expected_capacity_mbps} Mbps, found {actual:g} Mbps"
            )
        result = self.command_runner(
            self._command("bash", str(BOTTLENECK_SCRIPT), "off"),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if result.returncode != 0:
            raise ExperimentError(
                result.stderr.strip()
                or f"set_bottleneck.sh off exited with status {result.returncode}"
            )
        root_after, raw_after = self.qdisc_reader()
        if root_after.get("kind") != "noqueue":
            raise ExperimentError(
                f"bottleneck removal did not restore noqueue: {raw_after.strip()}"
            )
        self.expected_capacity_mbps = None


def wait_for_schedule(
    events: tuple[CapacityEvent, ...],
    *,
    start_time: float,
    set_capacity: Callable[[int], object],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Apply the scheduled changes using monotonic offsets from collection start."""
    for event in events:
        delay = start_time + event.offset_s - monotonic()
        if delay > 0:
            sleep(delay)
        set_capacity(event.capacity_mbps)


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        return connection.connect_ex((host, port)) == 0


def _free_tcp_port(candidates: tuple[int, ...]) -> int:
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("0.0.0.0", port))
            except OSError:
                continue
            return port
    raise ExperimentError("no free TCP port available for the third iperf3 server")


def _traffic_command(client: str, port: int, duration: float) -> list[str]:
    prefix = ["sudo", "-n"] if os.geteuid() != 0 else []
    return [
        *prefix,
        "ip",
        "netns",
        "exec",
        client,
        "iperf3",
        "-c",
        "10.50.0.1",
        "-p",
        str(port),
        "-t",
        str(math.ceil(duration)),
        "-R",
    ]


def _collector_command(
    *,
    output_path: Path,
    run_id: str,
    scenario_id: str,
    scenario: str,
    seed: int,
    sampling_interval: float,
    sampling_tolerance: float,
    duration: float,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "experiments.capacity_forecasting.collect_gateway_telemetry",
        "--output-file",
        str(output_path),
        "--run-id",
        run_id,
        "--scenario-id",
        scenario_id,
        "--scenario-type",
        scenario,
        "--random-seed",
        str(seed),
        "--traffic-profile",
        TRAFFIC_PROFILE,
        "--sampling-interval",
        str(sampling_interval),
        "--sampling-tolerance",
        str(sampling_tolerance),
        "--duration",
        str(duration),
    ]


def _validate_lab_prerequisites() -> int:
    for executable in ("tc", "ip", "iperf3"):
        if shutil.which(executable) is None:
            raise ExperimentError(f"required executable not found: {executable}")
    for client in CLIENT_NAMES:
        interface = f"veth-c{client[-1]}-br"
        result = subprocess.run(
            ["ip", "-o", "link", "show", "dev", interface],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ExperimentError(f"required interface is unavailable: {interface}")
        statistics = Path("/sys/class/net") / interface / "statistics"
        for counter in ("tx_bytes", "rx_bytes"):
            if not (statistics / counter).is_file():
                raise ExperimentError(f"collector counter is unavailable: {statistics / counter}")
    namespaces = subprocess.run(
        ["ip", "netns", "list"], capture_output=True, text=True, check=False
    )
    if namespaces.returncode != 0:
        raise ExperimentError("could not list network namespaces")
    namespace_names = {line.split()[0] for line in namespaces.stdout.splitlines() if line}
    missing = {client for client in CLIENT_NAMES} - namespace_names
    if missing:
        raise ExperimentError(f"required client namespaces are missing: {sorted(missing)}")
    for port in EXISTING_SERVER_PORTS:
        if not _port_is_open("10.50.0.1", port):
            raise ExperimentError(
                f"no iperf3 server reachable at 10.50.0.1:{port}; "
                "start the existing lab servers before collection"
            )
    if os.geteuid() != 0:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ExperimentError(
                "the documented set_bottleneck.sh workflow and namespace traffic "
                "require sudo; non-interactive sudo authorization is unavailable"
            )
    return _free_tcp_port(MANAGED_SERVER_PORTS)


def _assert_no_competing_clients() -> None:
    result = subprocess.run(
        ["ps", "-eo", "args="], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ExperimentError("could not inspect running processes")
    conflicts = [
        line.strip()
        for line in result.stdout.splitlines()
        if (
            "experiments/run_call_vs_download.py" in line
            or "experiments/run_streaming_vs_download.py" in line
            or "iperf3 -c " in line
        )
        and "run_capacity_experiment.py" not in line
        and "ps -eo args=" not in line
    ]
    if conflicts:
        raise ExperimentError(
            "another experiment or iperf3 client may be using the lab: "
            + "; ".join(conflicts)
        )


def _unique_output_paths(
    output_dir: Path, run_id: str
) -> tuple[Path, Path, Path, Path, Path]:
    stem = f"capacity_{run_id}"
    paths = (
        output_dir / f"{stem}.csv",
        output_dir / f"{stem}_metadata.json",
        output_dir / f"{stem}_collector.log",
        output_dir / f"{stem}_iperf3.log",
        output_dir / f"{stem}_iperf3_server.log",
    )
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing run output: " + ", ".join(existing)
        )
    return paths


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _stop_process(process: subprocess.Popen, *, interrupt: bool = False) -> None:
    if process.poll() is not None:
        return
    try:
        if interrupt:
            process.send_signal(signal.SIGINT)
        else:
            process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _cleanup_resources(
    traffic: list[subprocess.Popen],
    collector: subprocess.Popen | None,
    server: subprocess.Popen | None,
    bottleneck: BottleneckManager,
) -> str | None:
    for process in traffic:
        _stop_process(process)
    if collector is not None and collector.poll() is None:
        _stop_process(collector, interrupt=True)
    if server is not None:
        _stop_process(server)
    try:
        bottleneck.cleanup()
    except (ExperimentError, OSError, subprocess.SubprocessError) as error:
        return str(error)
    return None


def _run(args: argparse.Namespace) -> int:
    events = scenario_schedule(args.scenario, args.duration)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    (
        csv_path,
        manifest_path,
        collector_log_path,
        traffic_log_path,
        server_log_path,
    ) = (
        _unique_output_paths(output_dir, run_id)
    )
    randomizer = random.Random(args.seed)
    launch_delays = {
        client: randomizer.uniform(0.0, 0.15) for client in CLIENT_NAMES
    }

    _assert_no_competing_clients()
    managed_port = _validate_lab_prerequisites()
    bottleneck = BottleneckManager()
    bottleneck.preflight()

    manifest: dict[str, object] = {
        "schema_version": "1.1",
        "scenario_id": args.scenario_id or f"{args.scenario}-{run_id[:8]}",
        "run_id": run_id,
        "scenario_type": args.scenario,
        "random_seed": args.seed,
        "traffic_profile": TRAFFIC_PROFILE,
        "traffic_configuration": {
            "tool": "iperf3",
            "direction": "reverse download",
            "protocol": "TCP",
            "clients": list(CLIENT_NAMES),
            "server_ports": [*EXISTING_SERVER_PORTS, managed_port],
            "duration_s": args.duration,
            "seeded_client_launch_delays_s": launch_delays,
        },
        "capacity_schedule": [asdict(event) for event in events],
        "sample_interval_s": args.sampling_interval,
        "sample_cadence_tolerance_s": args.sampling_tolerance,
        "duration_s": args.duration,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_csv": str(csv_path),
        "run_complete": False,
        "qdisc_snapshots": bottleneck.snapshots,
    }
    with manifest_path.open("x", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")

    server: subprocess.Popen | None = None
    collector: subprocess.Popen | None = None
    traffic: list[subprocess.Popen] = []
    success = False
    cleanup_error: str | None = None
    traffic_log: TextIO | None = None
    collector_log: TextIO | None = None
    server_log: TextIO | None = None
    try:
        bottleneck.set_capacity(events[0].capacity_mbps, initial=True)
        traffic_log = traffic_log_path.open("x", encoding="utf-8")
        collector_log = collector_log_path.open("x", encoding="utf-8")
        server_log = server_log_path.open("x", encoding="utf-8")
        server = subprocess.Popen(
            ["iperf3", "-s", "-p", str(managed_port)],
            stdout=server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 5.0
        while not _port_is_open("10.50.0.1", managed_port):
            if server.poll() is not None:
                raise ExperimentError("managed iperf3 server exited during startup")
            if time.monotonic() >= deadline:
                raise ExperimentError("managed iperf3 server did not become ready")
            time.sleep(0.05)

        for index, client in enumerate(CLIENT_NAMES):
            if launch_delays[client]:
                time.sleep(launch_delays[client])
            port = (*EXISTING_SERVER_PORTS, managed_port)[index]
            traffic.append(
                subprocess.Popen(
                    _traffic_command(client, port, args.duration + 5),
                    stdout=traffic_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            )

        collector_command = _collector_command(
            output_path=csv_path,
            run_id=run_id,
            scenario_id=str(manifest["scenario_id"]),
            scenario=args.scenario,
            seed=args.seed,
            sampling_interval=args.sampling_interval,
            sampling_tolerance=args.sampling_tolerance,
            duration=args.duration,
        )
        collector_start = time.monotonic()
        manifest["collector_started_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["run_id"] = run_id
        manifest["csv_filename_run_id"] = csv_path.stem.removeprefix("capacity_")
        manifest["collector_command"] = collector_command
        collector = subprocess.Popen(
            collector_command,
            cwd=REPOSITORY_ROOT,
            stdout=collector_log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        for event in events[1:]:
            delay = collector_start + event.offset_s - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            if collector.poll() is not None:
                raise ExperimentError(
                    f"collector exited early with status {collector.returncode}"
                )
            bottleneck.set_capacity(event.capacity_mbps)
        collector_status = collector.wait(timeout=args.duration + 15)
        collector_log.flush()
        if collector_status != 0:
            raise ExperimentError(
                f"collector exited with status {collector_status}; "
                f"see {collector_log_path}"
            )

        failed_traffic = []
        for process in traffic:
            try:
                status = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                failed_traffic.append((process.pid, "still running"))
                continue
            if status != 0:
                failed_traffic.append((process.pid, status))
        if failed_traffic:
            raise ExperimentError(
                f"one or more iperf3 clients failed (pid, status): {failed_traffic}; "
                f"see {traffic_log_path}"
            )
        success = True
        manifest["run_complete"] = True
    except KeyboardInterrupt:
        manifest["interrupted"] = True
        raise
    finally:
        cleanup_error = _cleanup_resources(traffic, collector, server, bottleneck)
        for stream in (traffic_log, collector_log, server_log):
            if stream is not None:
                stream.close()
        manifest["run_complete"] = success
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["qdisc_snapshots"] = bottleneck.snapshots
        if cleanup_error:
            manifest["cleanup_error"] = cleanup_error
        _write_manifest(manifest_path, manifest)
        print(f"run_id={run_id}")
        print(f"scenario={manifest['scenario_id']}")
        print(f"csv={csv_path}")
        print(f"metadata={manifest_path}")
        print(f"run_complete={str(success).lower()}")
        if cleanup_error:
            print(f"cleanup_error={cleanup_error}", file=sys.stderr)
    if cleanup_error:
        raise ExperimentError(f"experiment cleanup failed: {cleanup_error}")
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run controlled three-client traffic and collect configured gateway "
            "capacity without using the gateway API."
        )
    )
    parser.add_argument(
        "--scenario",
        choices=("constant", "step", "periodic"),
        default="constant",
    )
    parser.add_argument("--scenario-id")
    parser.add_argument("--seed", type=int, default=secrets.randbits(32))
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument(
        "--sampling-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL
    )
    parser.add_argument(
        "--sampling-tolerance",
        type=float,
        default=0.25,
        help="maximum cadence deviation in seconds for a valid regular sample",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive and finite")
    if (
        not math.isfinite(args.sampling_interval)
        or args.sampling_interval <= 0
    ):
        parser.error("--sampling-interval must be positive and finite")
    if (
        not math.isfinite(args.sampling_tolerance)
        or args.sampling_tolerance < 0
    ):
        parser.error("--sampling-tolerance must be non-negative and finite")
    try:
        return _run(args)
    except (ExperimentError, FileExistsError, OSError, subprocess.SubprocessError) as error:
        print(f"experiment failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

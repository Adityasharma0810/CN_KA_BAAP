#!/usr/bin/env python3
"""Real Linux namespace/veth integration check for per-client accounting.

Run as root from the repository root:

    sudo .venv/bin/python scripts/run_lab_accounting_integration.py

The script uses only the project-owned lab scripts and real sysfs interface
counters. It does not inspect packet payloads and does not print MAC addresses.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.client_registry import AnonymousClientRegistry
from gateway.accounting import (
    PerClientAccountingCollector,
    SysfsCounterReader,
    build_lab_inventory,
)

BRIDGE = "br-lab"
PREFIX = "10.50.0"
NAT_TABLE = "eb_nat"
MATERIAL_BYTES = 4_000_000
# Broadcast/control frames (for example ARP or IPv6 discovery) can add a few
# hundred bytes to an otherwise idle bridge port. They are not client traffic.
ISOLATION_TOLERANCE_BYTES = 16_384
IDLE_RATE_TOLERANCE_MBPS = 0.01
UNRELATED_NS = "client99"
UNRELATED_BRIDGE = "br-unrelated"
UNRELATED_VETH = "veth-c99-br"
UNRELATED_TABLE = "eb_unrelated"
UNRELATED_DNS = Path("/etc/netns/client98")


class CheckFailure(RuntimeError):
    pass


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def section(self, title: str) -> None:
        self.line(f"\n=== {title} ===")

    def info(self, message: str) -> None:
        self.line(f"[INFO] {message}")

    def passed(self, message: str) -> None:
        self.line(f"[PASS] {message}")

    def failed(self, message: str) -> None:
        self.line(f"[FAIL] {message}")

    def line(self, message: str) -> None:
        self.lines.append(message)
        print(message, flush=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def run_command(*command: str, timeout: float = 30, check_status: bool = True):
    result = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check_status and result.returncode != 0:
        raise CheckFailure(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )
    return result


def run_lab_script(name: str, *args: str) -> None:
    run_command("bash", str(REPO_ROOT / "scripts" / name), *args, timeout=120)


def namespace_exists(name: str) -> bool:
    result = run_command("ip", "netns", "list", check_status=False)
    return any(line.split() and line.split()[0] == name for line in result.stdout.splitlines())


def interface_exists(name: str) -> bool:
    return (Path("/sys/class/net") / name).exists()


def nft_table_exists(name: str) -> bool:
    result = run_command("nft", "list", "table", "ip", name, check_status=False)
    return result.returncode == 0


def address(number: int) -> str:
    return f"{PREFIX}.{10 + number}"


def collect_by_number(
    collector: PerClientAccountingCollector,
) -> dict[int, object]:
    measurements = collector.collect()
    return {
        client.client_number: measurement
        for client, measurement in zip(collector.clients, measurements)
    }


def raw(measurement) -> tuple[int, int]:
    observation = measurement.observation
    return observation.download_bytes, observation.upload_bytes


def byte_delta(after, before, number: int) -> tuple[int, int]:
    after_down, after_up = raw(after[number])
    before_down, before_up = raw(before[number])
    return after_down - before_down, after_up - before_up


def _connect_with_retry(host: str, port: int, timeout: float = 8.0) -> socket.socket:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            return socket.create_connection((host, port), timeout=2)
        except OSError as error:
            last_error = error
            time.sleep(0.05)
    raise CheckFailure(f"could not connect to {host}:{port}: {last_error}")


def generate_download(number: int, size: int = 8_000_000) -> None:
    """Send bytes from the gateway into one namespace (client download)."""

    ns = f"client{number}"
    port = 21000 + number
    server_code = f"""
import socket
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", {port}))
s.listen(1)
c, _ = s.accept()
while True:
    data = c.recv(65536)
    if not data:
        break
c.close()
s.close()
"""
    server = subprocess.Popen(
        ["ip", "netns", "exec", ns, sys.executable, "-c", server_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        connection = _connect_with_retry(address(number), port)
        try:
            connection.sendall(b"x" * size)
            connection.shutdown(socket.SHUT_WR)
        finally:
            connection.close()
        _, stderr = server.communicate(timeout=20)
        if server.returncode != 0:
            raise CheckFailure(f"download sink for {ns} failed: {stderr.strip()}")
    finally:
        if server.poll() is None:
            server.kill()


def generate_upload(number: int, size: int = 8_000_000) -> None:
    """Send bytes from one namespace to the gateway (client upload)."""

    ns = f"client{number}"
    port = 22000 + number
    ready = threading.Event()
    errors: list[BaseException] = []
    received: list[int] = []

    def sink() -> None:
        try:
            server = socket.socket()
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((f"{PREFIX}.1", port))
            server.listen(1)
            ready.set()
            connection, _ = server.accept()
            total = 0
            while True:
                data = connection.recv(65536)
                if not data:
                    break
                total += len(data)
            received.append(total)
            connection.close()
            server.close()
        except BaseException as error:  # surfaced in the main thread
            errors.append(error)
            ready.set()

    thread = threading.Thread(target=sink, daemon=True)
    thread.start()
    ready.wait(timeout=5)
    if errors:
        raise CheckFailure(f"upload sink failed: {errors[0]}")
    client_code = f"""
import socket
s = socket.socket()
s.connect(("{PREFIX}.1", {port}))
s.sendall(b"x" * {size})
s.shutdown(socket.SHUT_WR)
s.close()
"""
    try:
        run_command("ip", "netns", "exec", ns, sys.executable, "-c", client_code, timeout=30)
    finally:
        thread.join(timeout=20)
    if errors:
        raise CheckFailure(f"upload sink failed: {errors[0]}")
    check(bool(received), f"upload sink for {ns} received no data")


def verify_resources(report: Report, count: int) -> None:
    for number in range(1, count + 1):
        check(namespace_exists(f"client{number}"), f"client{number} namespace missing")
        check(interface_exists(f"veth-c{number}-br"), f"veth-c{number}-br missing")
        check(Path(f"/etc/netns/client{number}/resolv.conf").is_file(),
              f"client{number} DNS file missing")
    check(interface_exists(BRIDGE), f"{BRIDGE} missing")
    check(nft_table_exists(NAT_TABLE), f"{NAT_TABLE} missing")
    report.passed(f"{count}-client resources and DNS configuration present")


def verify_connectivity(report: Report, count: int) -> None:
    for number in range(1, count + 1):
        result = run_command(
            "ip", "netns", "exec", f"client{number}",
            "ping", "-c", "1", "-W", "2", f"{PREFIX}.1",
            check_status=False,
        )
        check(result.returncode == 0, f"client{number} cannot reach gateway")
    if count >= 2:
        result = run_command(
            "ip", "netns", "exec", "client1",
            "ping", "-c", "1", "-W", "2", address(2),
            check_status=False,
        )
        check(result.returncode == 0, "client1 cannot reach client2")
    report.passed(f"{count}-client gateway and inter-client connectivity")


def create_unrelated_resources() -> None:
    cleanup_unrelated_resources()
    run_command("ip", "netns", "add", UNRELATED_NS)
    run_command("ip", "link", "add", UNRELATED_BRIDGE, "type", "bridge")
    run_command("ip", "link", "add", UNRELATED_VETH, "type", "dummy")
    run_command("nft", "add", "table", "ip", UNRELATED_TABLE)
    UNRELATED_DNS.mkdir(parents=True, exist_ok=True)
    (UNRELATED_DNS / "resolv.conf").write_text("nameserver 1.1.1.1\n", encoding="ascii")


def verify_unrelated_resources(report: Report) -> None:
    check(namespace_exists(UNRELATED_NS), "cleanup removed unrelated namespace")
    check(interface_exists(UNRELATED_BRIDGE), "cleanup removed unrelated bridge")
    check(interface_exists(UNRELATED_VETH), "cleanup removed unrelated interface")
    check(nft_table_exists(UNRELATED_TABLE), "cleanup removed unrelated nft table")
    check(UNRELATED_DNS.is_dir(), "cleanup removed unrelated DNS directory")
    report.passed("cleanup left unrelated namespace/interface/bridge/nft/DNS untouched")


def cleanup_unrelated_resources() -> None:
    run_command("ip", "netns", "del", UNRELATED_NS, check_status=False)
    run_command("ip", "link", "del", UNRELATED_VETH, check_status=False)
    run_command("ip", "link", "del", UNRELATED_BRIDGE, check_status=False)
    run_command("nft", "delete", "table", "ip", UNRELATED_TABLE, check_status=False)
    shutil.rmtree(UNRELATED_DNS, ignore_errors=True)


def verify_cleanup(report: Report, count: int) -> None:
    for number in range(1, count + 1):
        check(not namespace_exists(f"client{number}"), f"client{number} still exists")
        check(not interface_exists(f"veth-c{number}-br"), f"veth-c{number}-br still exists")
        check(not Path(f"/etc/netns/client{number}").exists(),
              f"client{number} DNS directory still exists")
    check(not interface_exists(BRIDGE), f"{BRIDGE} still exists")
    check(not nft_table_exists(NAT_TABLE), f"{NAT_TABLE} still exists")
    report.passed(f"{count}-client project resources removed")


def run_count(report: Report, count: int) -> None:
    report.section(f"{count}-client real Linux accounting")

    run_lab_script("cleanup_gateway.sh", str(count))
    run_lab_script("setup_gateway.sh", str(count))
    run_lab_script("setup_gateway.sh", str(count))
    report.passed("setup is idempotent")
    verify_resources(report, count)
    verify_connectivity(report, count)

    registry = AnonymousClientRegistry()
    inventory = build_lab_inventory(registry, client_numbers=tuple(range(1, count + 1)))
    collector = PerClientAccountingCollector(
        inventory,
        registry,
        reader=SysfsCounterReader(),
    )

    first = collect_by_number(collector)
    check(
        all(item.rate_reason == "no_baseline" for item in first.values()),
        "first sample should have no rate baseline",
    )
    report.passed("baseline counters collected from real sysfs interfaces")

    # Download only for client 1.
    generate_download(1)
    after_download = collect_by_number(collector)
    down, up = byte_delta(after_download, first, 1)
    check(down >= MATERIAL_BYTES, f"client1 download delta too small: {down}")
    check(up < max(down // 10, 1), f"client1 upload contaminated download test: {up}")
    other_deltas = []
    for number in range(2, count + 1):
        other_down, other_up = byte_delta(after_download, first, number)
        other_deltas.append((number, other_down, other_up))
        check(other_down <= ISOLATION_TOLERANCE_BYTES,
              f"client{number} download changed during client1 test: {other_down}")
        check(other_up <= ISOLATION_TOLERANCE_BYTES,
              f"client{number} upload changed during client1 test: {other_up}")
    report.passed(
        f"download isolation: client1 down={down} B up={up} B; "
        f"non-target max={max((max(d, u) for _, d, u in other_deltas), default=0)} B "
        f"(tolerance {ISOLATION_TOLERANCE_BYTES} B)"
    )

    # Upload only for client 2.
    generate_upload(2)
    after_upload = collect_by_number(collector)
    down, up = byte_delta(after_upload, after_download, 2)
    check(up >= MATERIAL_BYTES, f"client2 upload delta too small: {up}")
    check(down < max(up // 10, 1), f"client2 download contaminated upload test: {down}")
    other_deltas = []
    for number in range(1, count + 1):
        if number == 2:
            continue
        other_down, other_up = byte_delta(after_upload, after_download, number)
        other_deltas.append((number, other_down, other_up))
        check(other_down <= ISOLATION_TOLERANCE_BYTES,
              f"client{number} download changed during client2 test: {other_down}")
        check(other_up <= ISOLATION_TOLERANCE_BYTES,
              f"client{number} upload changed during client2 test: {other_up}")
    report.passed(
        f"upload isolation: client2 up={up} B down={down} B; "
        f"non-target max={max((max(d, u) for _, d, u in other_deltas), default=0)} B "
        f"(tolerance {ISOLATION_TOLERANCE_BYTES} B)"
    )

    # Simultaneous traffic on multiple clients.
    before_simultaneous = collect_by_number(collector)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(generate_download, 1),
            executor.submit(generate_upload, 2),
        ]
        if count >= 3:
            futures.append(executor.submit(generate_download, 3))
        for future in futures:
            future.result()
    after_simultaneous = collect_by_number(collector)

    down1, up1 = byte_delta(after_simultaneous, before_simultaneous, 1)
    down2, up2 = byte_delta(after_simultaneous, before_simultaneous, 2)
    check(down1 >= MATERIAL_BYTES, f"client1 simultaneous download too small: {down1}")
    check(up1 < max(down1 // 10, 1), f"client1 simultaneous upload contaminated: {up1}")
    check(up2 >= MATERIAL_BYTES, f"client2 simultaneous upload too small: {up2}")
    check(down2 < max(up2 // 10, 1), f"client2 simultaneous download contaminated: {down2}")
    if count >= 3:
        down3, up3 = byte_delta(after_simultaneous, before_simultaneous, 3)
        check(down3 >= MATERIAL_BYTES, f"client3 simultaneous download too small: {down3}")
        check(up3 < max(down3 // 10, 1), f"client3 simultaneous upload contaminated: {up3}")
    for number in range(4, count + 1):
        other_down, other_up = byte_delta(after_simultaneous, before_simultaneous, number)
        check(other_down <= ISOLATION_TOLERANCE_BYTES,
              f"idle client{number} download changed: {other_down}")
        check(other_up <= ISOLATION_TOLERANCE_BYTES,
              f"idle client{number} upload changed: {other_up}")
    report.passed("simultaneous multi-client traffic remained independent")

    # Stop traffic and check idle rates. Broadcast/control frames may remain,
    # but no client may show material byte or rate changes.
    before_idle = collect_by_number(collector)
    time.sleep(1.2)
    after_idle = collect_by_number(collector)
    idle_values = []
    for number in range(1, count + 1):
        idle_down, idle_up = byte_delta(after_idle, before_idle, number)
        observation = after_idle[number].observation
        idle_values.append((number, idle_down, idle_up,
                            observation.download_mbps, observation.upload_mbps))
        check(idle_down <= ISOLATION_TOLERANCE_BYTES,
              f"client{number} still downloading while idle: {idle_down}")
        check(idle_up <= ISOLATION_TOLERANCE_BYTES,
              f"client{number} still uploading while idle: {idle_up}")
        check(observation.download_mbps <= IDLE_RATE_TOLERANCE_MBPS,
              f"client{number} idle download rate too high: {observation.download_mbps}")
        check(observation.upload_mbps <= IDLE_RATE_TOLERANCE_MBPS,
              f"client{number} idle upload rate too high: {observation.upload_mbps}")
    max_idle_rate = max(max(row[3], row[4]) for row in idle_values)
    report.passed(
        f"idle clients: max byte change={max(max(row[1], row[2]) for row in idle_values)} B, "
        f"max rate={max_idle_rate:.6f} Mbit/s "
        f"(tolerances {ISOLATION_TOLERANCE_BYTES} B, {IDLE_RATE_TOLERANCE_MBPS} Mbit/s)"
    )

    # Remove one client and verify failure isolation.
    removed = count
    run_command("ip", "netns", "del", f"client{removed}")
    after_missing = collect_by_number(collector)
    missing = after_missing[removed]
    check(missing.rate_reason == "interface_unavailable",
          f"removed client reason was {missing.rate_reason!r}")
    check(missing.observation.metadata.quality == "unavailable",
          "removed client observation was not unavailable")
    for number in range(1, count):
        check(after_missing[number].rate_reason is None,
              f"client{number} failed when client{removed} disappeared")
    report.passed(f"interface disappearance isolated to client{removed}")

    # Recreate the removed client; its new zero counters must be detected as a reset.
    run_lab_script("setup_gateway.sh", str(count))
    after_recreate = collect_by_number(collector)
    check(after_recreate[removed].rate_reason == "counter_reset",
          f"recreated client reason was {after_recreate[removed].rate_reason!r}")
    for number in range(1, count):
        check(after_recreate[number].rate_reason != "counter_reset",
              f"client{number} was incorrectly flagged as reset")
    report.passed(f"counter reset detected for recreated client{removed}")

    # Cleanup ownership and idempotence.
    create_unrelated_resources()
    run_lab_script("cleanup_gateway.sh", str(count))
    run_lab_script("cleanup_gateway.sh", str(count))
    report.passed("cleanup is idempotent")
    verify_cleanup(report, count)
    verify_unrelated_resources(report)
    cleanup_unrelated_resources()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence",
        default="/tmp/opencode/module3_lab_evidence.txt",
        help="path for the concise evidence log",
    )
    parser.add_argument(
        "--counts",
        default="3,5",
        help="comma-separated client counts to test",
    )
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("Run as root: sudo .venv/bin/python scripts/run_lab_accounting_integration.py", file=sys.stderr)
        return 2

    counts = tuple(int(value) for value in args.counts.split(",") if value.strip())
    report = Report()
    report.section("Environment")
    report.info(f"kernel: {os.uname().release}")
    report.info(f"python: {sys.version.split()[0]}")
    report.info(f"client counts: {', '.join(map(str, counts))}")
    default_route = run_command("ip", "route", "show", "default", check_status=False)
    report.info(f"default route: {default_route.stdout.strip() or 'none'}")
    report.info(f"ip_forward before: {Path('/proc/sys/net/ipv4/ip_forward').read_text().strip()}")

    exit_code = 0
    try:
        for count in counts:
            run_count(report, count)
        report.section("RESULT")
        report.passed("all requested real Linux accounting checks passed")
    except BaseException as error:
        exit_code = 1
        report.section("FAILURE")
        report.failed(str(error))
        report.line(traceback.format_exc())
        try:
            for count in counts:
                run_lab_script("cleanup_gateway.sh", str(count))
        except BaseException:
            pass
        cleanup_unrelated_resources()
    finally:
        evidence_path = Path(args.evidence)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("\n".join(report.lines) + "\n", encoding="utf-8")
        evidence_path.chmod(0o644)
        print(f"\nEvidence written to {evidence_path}", flush=True)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

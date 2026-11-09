#!/usr/bin/env python3
"""Reads per-client traffic counters from the lab bridge ports."""
import time

from backend.app.services.client_registry import AnonymousClientRegistry
from gateway.accounting import (
    SysfsCounterReader,
    build_lab_inventory,
    client_numbers_from_environment,
)

CLIENTS = list(client_numbers_from_environment())
INTERVAL = 1.0

# Runtime-only registry. IDs change on process restart and contain no device data.
registry = AnonymousClientRegistry()
inventory = build_lab_inventory(registry, client_numbers=CLIENTS)
anon_ids = {client.client_number: client.client_id for client in inventory}
_counter_reader = SysfsCounterReader()


def read_bytes(client: int) -> tuple[int, int]:
    """Return (download_bytes, upload_bytes) for one lab client.

    The shared reader observes only the gateway-side veth endpoint. Its TX
    counters represent bytes sent toward the namespace (client download), and
    RX counters represent bytes sent from the namespace (client upload).
    """
    config = next((item for item in inventory if item.client_number == client), None)
    if config is None:
        raise ValueError(f"Unknown lab client: {client}")
    snapshot = _counter_reader(config.gateway_interface)
    return snapshot.transmitted_bytes, snapshot.received_bytes


def main() -> None:
    try:
        prev = {c: read_bytes(c) for c in CLIENTS}
    except (FileNotFoundError, RuntimeError, OSError):
        print("Lab not found. Run: sudo bash scripts/setup_gateway.sh")
        return

    prev_t = time.monotonic()
    print(f"{'ID':<12}{'Down Mbit/s':>14}{'Up Mbit/s':>12}")
    while True:
        time.sleep(INTERVAL)
        now = time.monotonic()
        dt = now - prev_t
        for c in CLIENTS:
            down, up = read_bytes(c)
            d_mbps = (down - prev[c][0]) * 8 / dt / 1e6
            u_mbps = (up - prev[c][1]) * 8 / dt / 1e6
            print(f"{anon_ids[c]:<12}{d_mbps:>14.1f}{u_mbps:>12.1f}")
            prev[c] = (down, up)
        prev_t = now
        print("-" * 38)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
#!/usr/bin/env python3
"""Reads per-client traffic counters from the lab bridge ports."""
import secrets
import time
from pathlib import Path

CLIENTS = [1, 2, 3]
INTERVAL = 1.0

# Anonymous IDs live in memory only and change on every restart.
anon_ids = {c: "dev-" + secrets.token_hex(3) for c in CLIENTS}


def read_bytes(client: int) -> tuple[int, int]:
    """Return (download_bytes, upload_bytes) for a client.

    We read the bridge-side end of the veth cable, so directions flip:
    what the bridge transmits is what the client downloads.
    """
    base = Path(f"/sys/class/net/veth-c{client}-br/statistics")
    down = int((base / "tx_bytes").read_text())
    up = int((base / "rx_bytes").read_text())
    return down, up


def main() -> None:
    try:
        prev = {c: read_bytes(c) for c in CLIENTS}
    except FileNotFoundError:
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
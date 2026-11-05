
"""
Experience Budget - V0.3
Internet Connectivity Monitor.

Privacy:
- Checks only the laptop's selected network adapter.
- Does not discover connected devices.
- Does not collect IP addresses or MAC addresses.
- Does not inspect packets or payloads.
- Uses brief TCP connection probes; sends no application data.
"""

import argparse
import json
import socket
import time

from datetime import datetime, timezone

import psutil


# Independent public reachability probes.
# Only a TCP connection attempt is made; no application data is sent.
PROBE_ENDPOINTS = [
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
]


def get_adapter_status(adapter_name: str) -> bool:
    """Return the operating-system status of the local adapter."""

    interfaces = psutil.net_if_stats()

    if adapter_name not in interfaces:
        raise RuntimeError(
            f"Adapter '{adapter_name}' was not found."
        )

    return bool(interfaces[adapter_name].isup)


def probe_internet(timeout: float = 2.0) -> tuple:
    """Test reachability through independent public endpoints."""

    successful_probes = 0

    for host, port in PROBE_ENDPOINTS:
        connection = None

        try:
            connection = socket.create_connection(
                (host, port),
                timeout=timeout
            )
            successful_probes += 1

        except OSError:
            pass

        finally:
            if connection is not None:
                connection.close()

    return (
        successful_probes > 0,
        successful_probes,
        len(PROBE_ENDPOINTS),
    )


def collect_connectivity(
    adapter_name: str = "Wi-Fi",
    timeout: float = 2.0
) -> dict:
    """Collect a privacy-safe connectivity snapshot."""

    adapter_up = get_adapter_status(adapter_name)

    if adapter_up:
        internet_reachable, successful, total = probe_internet(
            timeout
        )
    else:
        internet_reachable = False
        successful = 0
        total = 0

    if not adapter_up:
        status = "adapter_down"
    elif internet_reachable:
        status = "online"
    else:
        status = "internet_unreachable"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interface": adapter_name,
        "adapter_up": adapter_up,
        "internet_reachable": internet_reachable,
        "successful_probes": successful,
        "total_probes": total,
        "status": status,
        "scope": "local_connectivity_only",
    }


class OutageTracker:
    """Track outage duration and recovery events."""

    def __init__(self):
        self.outage_started_at = None

    def update(self, reachable: bool, now=None) -> dict:
        if now is None:
            now = time.monotonic()

        if reachable:
            if self.outage_started_at is not None:
                duration = now - self.outage_started_at
                self.outage_started_at = None

                return {
                    "outage_duration_seconds": 0,
                    "outage_recovered": True,
                    "last_outage_duration_seconds": round(
                        duration, 2
                    ),
                }

            return {
                "outage_duration_seconds": 0,
                "outage_recovered": False,
            }

        if self.outage_started_at is None:
            self.outage_started_at = now

        duration = now - self.outage_started_at

        return {
            "outage_duration_seconds": round(duration, 2),
            "outage_recovered": False,
        }


def monitor(
    adapter: str,
    interval: float,
    samples: int,
    timeout: float
):
    """Continuously monitor connectivity and outage duration."""

    tracker = OutageTracker()

    print(f"Monitoring adapter: {adapter}")
    print("Press Ctrl+C to stop.\n")

    for index in range(samples):
        if index > 0:
            time.sleep(interval)

        snapshot = collect_connectivity(
            adapter,
            timeout
        )

        outage = tracker.update(
            snapshot["internet_reachable"]
        )

        snapshot.update(outage)

        print(json.dumps(snapshot), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Experience Budget connectivity monitor"
    )

    parser.add_argument("--adapter", default="Wi-Fi")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=2.0)

    args = parser.parse_args()

    if args.interval <= 0 or args.samples <= 0 or args.timeout <= 0:
        parser.error("Interval, samples and timeout must be positive")

    try:
        monitor(
            args.adapter,
            args.interval,
            args.samples,
            args.timeout
        )
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    except RuntimeError as error:
        parser.exit(1, f"ERROR: {error}\n")

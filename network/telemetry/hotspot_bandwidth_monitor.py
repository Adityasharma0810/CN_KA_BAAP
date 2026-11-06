
"""
Experience Budget V0.8.2
Anonymous downstream hotspot traffic monitoring.

Measures aggregate traffic on the Windows Mobile Hotspot
virtual adapter. No client identities are collected.
"""

import argparse
import json
import time
from datetime import datetime, timezone

from network.telemetry.interface_stats import get_interface_stats
from network.telemetry.bandwidth_monitor import calculate_rates


def calculate_client_rates(previous, current, elapsed):
    """Translate host interface counters into client-side directions."""

    host_rates = calculate_rates(previous, current, elapsed)

    return {
        # Host transmits towards hotspot clients.
        "client_download_mbps": host_rates["upload_mbps"],

        # Host receives traffic from hotspot clients.
        "client_upload_mbps": host_rates["download_mbps"],

        "host_tx_bytes": host_rates["sent_bytes"],
        "host_rx_bytes": host_rates["received_bytes"],
        "elapsed_seconds": host_rates["elapsed_seconds"],
    }


def monitor(adapter, interval, samples):
    previous = get_interface_stats(adapter)
    previous_time = time.monotonic()

    print(f"Monitoring downstream interface: {adapter}")
    print("Aggregate client traffic only. Press Ctrl+C to stop.\n")

    for _ in range(samples):
        time.sleep(interval)

        current = get_interface_stats(adapter)
        current_time = time.monotonic()

        rates = calculate_client_rates(
            previous,
            current,
            current_time - previous_time,
        )

        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interface": adapter,
            **rates,
            "scope": "anonymous_downstream_aggregate",
        }

        print(json.dumps(output), flush=True)

        previous = current
        previous_time = current_time


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--adapter",
        default="Local Area Connection* 2",
    )

    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--samples", type=int, default=30)

    args = parser.parse_args()

    if args.interval <= 0 or args.samples <= 0:
        parser.error("Interval and samples must be positive.")

    try:
        monitor(args.adapter, args.interval, args.samples)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")


"""
Experience Budget - V0.2
Live aggregate bandwidth monitor.

Reads only the local adapter's cumulative byte counters.
No device discovery, packet inspection or traffic modification.
"""

import argparse
import json
import time
from datetime import datetime, timezone

from network.telemetry.interface_stats import get_interface_stats


def calculate_rates(previous, current, elapsed):
    """Calculate aggregate download and upload rates in Mbps."""

    if elapsed <= 0:
        raise ValueError("Elapsed time must be positive")

    received_delta = (
        current["received_bytes"] - previous["received_bytes"]
    )
    sent_delta = (
        current["sent_bytes"] - previous["sent_bytes"]
    )

    if received_delta < 0 or sent_delta < 0:
        raise ValueError(
            "Network counters decreased. Adapter may have reset."
        )

    download_mbps = received_delta * 8 / elapsed / 1_000_000
    upload_mbps = sent_delta * 8 / elapsed / 1_000_000

    return {
        "download_mbps": round(download_mbps, 3),
        "upload_mbps": round(upload_mbps, 3),
        "received_bytes": received_delta,
        "sent_bytes": sent_delta,
        "elapsed_seconds": round(elapsed, 3),
    }


def monitor(adapter, interval, samples):
    """Continuously measure local adapter throughput."""

    previous = get_interface_stats(adapter)
    previous_time = time.monotonic()

    print(f"Monitoring adapter: {adapter}")
    print("Press Ctrl+C to stop.\n")

    for _ in range(samples):
        time.sleep(interval)

        current = get_interface_stats(adapter)
        current_time = time.monotonic()

        elapsed = current_time - previous_time

        rates = calculate_rates(
            previous,
            current,
            elapsed
        )

        output = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "interface": adapter,
            **rates,
            "scope": "local_adapter_aggregate",
        }

        print(json.dumps(output), flush=True)

        previous = current
        previous_time = current_time


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--adapter",
        default="Wi-Fi"
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=30
    )

    args = parser.parse_args()

    if args.interval <= 0 or args.samples <= 0:
        parser.error("Interval and samples must be positive")

    try:
        monitor(args.adapter, args.interval, args.samples)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

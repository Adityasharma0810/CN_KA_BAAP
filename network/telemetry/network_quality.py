
"""
Experience Budget - V0.4
Network Quality Monitor.

Measures public-endpoint RTT, RTT variation and ICMP loss.

Privacy:
- Probes only explicitly selected public IP addresses.
- Does not discover or identify household devices.
- Does not inspect packet payloads.
- Does not capture browsing or application activity.
"""

import argparse
import ipaddress
import json
import re
import subprocess
import time

from datetime import datetime, timezone


PING_TIME_PATTERN = re.compile(
    r"\btime\s*([=<])\s*(\d+(?:\.\d+)?)\s*ms\b",
    re.IGNORECASE,
)


def ping_once(target: str, timeout_ms: int = 1000):
    """Send one ICMP probe and return RTT in milliseconds."""

    try:
        ipaddress.ip_address(target)
    except ValueError as error:
        raise ValueError(
            "Target must be a numeric IP address."
        ) from error

    if timeout_ms <= 0:
        raise ValueError("Timeout must be positive.")

    command = [
        "ping",
        "-n", "1",
        "-w", str(timeout_ms),
        target,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=(timeout_ms / 1000) + 3,
            check=False,
        )

    except subprocess.TimeoutExpired:
        return None

    except FileNotFoundError as error:
        raise RuntimeError(
            "Windows ping executable was not found."
        ) from error

    output = result.stdout + "\n" + result.stderr

    match = PING_TIME_PATTERN.search(output)

    if not match:
        return None

    operator = match.group(1)
    rtt = float(match.group(2))

    # Windows can report time<1ms.
    # Represent this as an approximate sub-millisecond result.
    if operator == "<":
        rtt /= 2

    return rtt


def summarize_rtts(rtts, probes_sent: int) -> dict:
    """Calculate RTT statistics, variation and packet loss."""

    if probes_sent <= 0:
        raise ValueError("At least one probe is required.")

    successful = [
        float(value)
        for value in rtts
        if value is not None
    ]

    if len(successful) > probes_sent:
        raise ValueError("More successful probes than probes sent.")

    lost = probes_sent - len(successful)

    packet_loss = (lost / probes_sent) * 100

    # Mean absolute difference between successive successful RTTs.
    differences = [
        abs(successful[i] - successful[i - 1])
        for i in range(1, len(successful))
    ]

    jitter = (
        sum(differences) / len(differences)
        if differences else None
    )

    return {
        "probes_sent": probes_sent,
        "probes_received": len(successful),
        "packet_loss_percent": round(packet_loss, 2),
        "rtt_min_ms": round(min(successful), 2) if successful else None,
        "rtt_avg_ms": round(
            sum(successful) / len(successful), 2
        ) if successful else None,
        "rtt_max_ms": round(max(successful), 2) if successful else None,
        "rtt_jitter_avg_ms": round(jitter, 2) if jitter is not None else None,
        "status": (
            "no_icmp_reply" if not successful
            else "packet_loss" if lost
            else "healthy"
        ),
    }


def measure_target(
    target: str,
    count: int = 10,
    interval: float = 1.0,
    timeout_ms: int = 1000,
) -> dict:
    """Collect multiple RTT samples from one public endpoint."""

    if count <= 0 or interval < 0 or timeout_ms <= 0:
        raise ValueError("Invalid measurement configuration.")

    rtts = []

    for index in range(count):
        rtt = ping_once(target, timeout_ms)
        rtts.append(rtt)

        if index < count - 1 and interval > 0:
            time.sleep(interval)

    return summarize_rtts(rtts, count)


def main():
    parser = argparse.ArgumentParser(
        description="Experience Budget Network Quality Monitor"
    )

    parser.add_argument(
        "--target",
        default="1.1.1.1",
        help="Public numeric IP address to probe."
    )

    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout-ms", type=int, default=1000)

    args = parser.parse_args()

    try:
        result = measure_target(
            target=args.target,
            count=args.count,
            interval=args.interval,
            timeout_ms=args.timeout_ms,
        )

        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target": args.target,
            **result,
            "jitter_definition": (
                "Mean absolute difference between successive "
                "successful RTT measurements"
            ),
            "scope": "public_endpoint_path_quality",
        }

        print(json.dumps(output, indent=4))

    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()

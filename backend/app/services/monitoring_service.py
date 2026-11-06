
"""
Experience Budget V0.6
Combines local aggregate network measurements and persists them.

Only measures the laptop's selected network interface and
explicitly approved public measurement endpoints.
"""

import time
from datetime import datetime, timezone

from network.telemetry.interface_stats import get_interface_stats
from network.telemetry.bandwidth_monitor import calculate_rates
from network.telemetry.connectivity_monitor import collect_connectivity
from network.telemetry.network_quality import measure_target
from network.telemetry.metrics_store import MetricsStore


ALLOWED_TARGETS = {"1.1.1.1", "8.8.8.8"}

DEFAULT_DB_PATH = "data/experience_budget.sqlite3"


def collect_and_store(
    adapter="Wi-Fi",
    sample_interval=1.0,
    quality_target="1.1.1.1",
    quality_count=5,
    db_path=DEFAULT_DB_PATH,
):
    """Collect and persist one aggregate monitoring sample."""

    if quality_target not in ALLOWED_TARGETS:
        raise ValueError("Unapproved measurement target.")

    if not 0 < sample_interval <= 5:
        raise ValueError("Sample interval must be between 0 and 5 seconds.")

    if not 1 <= quality_count <= 10:
        raise ValueError("Quality count must be between 1 and 10.")

    # 1. Measure aggregate interface throughput.
    previous = get_interface_stats(adapter)
    start = time.monotonic()

    time.sleep(sample_interval)

    current = get_interface_stats(adapter)
    elapsed = time.monotonic() - start

    bandwidth = calculate_rates(
        previous,
        current,
        elapsed,
    )

    # 2. Check connectivity.
    connectivity = collect_connectivity(
        adapter_name=adapter,
        timeout=1.0,
    )

    # 3. Measure network quality.
    quality = measure_target(
        target=quality_target,
        count=quality_count,
        interval=0.2,
        timeout_ms=1000,
    )

    # 4. Construct an aggregate-only database record.
    recorded_at = datetime.now(timezone.utc).isoformat()

    sample = {
        "recorded_at": recorded_at,
        "interface_label": adapter,
        "download_mbps": bandwidth["download_mbps"],
        "upload_mbps": bandwidth["upload_mbps"],
        "adapter_up": connectivity["adapter_up"],
        "internet_reachable": connectivity["internet_reachable"],
        "probe_target": quality_target,
        "probes_sent": quality["probes_sent"],
        "probes_received": quality["probes_received"],
        "packet_loss_percent": quality["packet_loss_percent"],
        "rtt_min_ms": quality["rtt_min_ms"],
        "rtt_avg_ms": quality["rtt_avg_ms"],
        "rtt_max_ms": quality["rtt_max_ms"],
        "rtt_jitter_avg_ms": quality["rtt_jitter_avg_ms"],
    }

    # 5. Persist the sample.
    store = MetricsStore(db_path)
    sample_id = store.insert_sample(sample)

    return {
        "sample_id": sample_id,
        "timestamp": recorded_at,
        "interface": adapter,
        "bandwidth": bandwidth,
        "connectivity": connectivity,
        "network_quality": quality,
        "scope": "local_aggregate_only",
    }


def get_history(limit=100, db_path=DEFAULT_DB_PATH):
    """Read historical aggregate network measurements."""

    store = MetricsStore(db_path)
    return store.get_recent_samples(limit)

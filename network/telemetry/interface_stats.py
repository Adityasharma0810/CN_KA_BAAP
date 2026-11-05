
"""
Experience Budget - V0.1
Local network interface statistics.

Privacy:
- Reads aggregate counters for one local adapter.
- Does not inspect connected devices or packet contents.
"""

import psutil


def get_interface_stats(adapter_name: str = "Wi-Fi") -> dict:
    """Read aggregate statistics for a local network adapter."""

    interfaces = psutil.net_io_counters(pernic=True)

    if not interfaces or adapter_name not in interfaces:
        available = ", ".join(sorted(interfaces or {}))
        raise RuntimeError(
            f"Adapter '{adapter_name}' not found. "
            f"Available interfaces: {available}"
        )

    stats = interfaces[adapter_name]

    return {
        "interface": adapter_name,
        "received_bytes": int(stats.bytes_recv),
        "sent_bytes": int(stats.bytes_sent),
        "receive_errors": int(stats.errin),
        "send_errors": int(stats.errout),
        "scope": "local_adapter_aggregate",
    }

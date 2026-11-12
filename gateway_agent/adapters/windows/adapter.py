"""Windows platform adapter (skeleton).

Windows does not provide a Linux-equivalent `tc`/CAKE facility. This adapter
reports honest capabilities: observation via adapter counters is possible;
traffic shaping requires third-party filters/WFP and is not claimed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from gateway_agent.core.config import AgentConfig
from gateway_agent.core.interfaces import (
    CapabilityReport,
    ClientInfo,
    InterfaceInfo,
    Observation,
    PlatformAdapter,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WindowsAdapter(PlatformAdapter):
    name = "windows"
    platform = "windows"

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    async def discover_interfaces(self) -> list[InterfaceInfo]:
        # Windows adapter discovery would use netsh/WMI; kept minimal to avoid
        # hard dependencies. Returns empty until implemented.
        return []

    async def detect_capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            can_monitor_upstream=True,
            can_monitor_downstream=True,
            can_discover_clients=False,
            can_attribute_client_traffic=False,
            can_manage_access_point=False,
            can_enable_forwarding=False,
            can_enable_nat=False,
            can_apply_upload_shaping=False,
            can_apply_download_shaping=False,
            supported_qdiscs=(),
            can_collect_queue_stats=False,
            can_collect_wifi_stats=False,
            can_multi_wan=True,
            can_policy_routing=False,
            can_recover_state=True,
            simultaneous_wifi_client_ap=False,
            notes=(
                "Observation-only on Windows. Native traffic shaping is not "
                "available through this adapter; use a Linux gateway or "
                "supported router for enforcement."
            ),
        )

    async def discover_clients(self) -> list[ClientInfo]:
        return []

    async def collect_observations(self) -> list[Observation]:
        return []

    async def enable_ip_forwarding(self) -> bool:
        return False

    async def enable_nat(self) -> bool:
        return False

    async def apply_policy(self, allocations: dict[str, dict]) -> dict:
        return {"mode": "none", "applied": {}, "error": "shaping_unsupported_on_windows"}

    async def read_back_state(self) -> dict:
        return {"platform": "windows", "shaping": "unsupported"}

    async def rollback(self) -> bool:
        return True

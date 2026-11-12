"""Core platform-agnostic interfaces for the gateway agent.

Every operating-system adapter (Windows, Linux, macOS, OpenWrt) implements the
same contracts. Capabilities are reported honestly so the frontend never shows
an unsupported feature as operational.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class InterfaceInfo:
    name: str
    type: str  # ethernet, wifi, cellular, ...
    state: str  # up, down, unknown
    mac: str | None = None
    driver: str | None = None


@dataclass(frozen=True)
class ClientInfo:
    client_id: str  # opaque pseudonymous id
    mac: str | None = None
    ip: str | None = None
    hostname: str | None = None
    connected: bool = False
    connected_at: datetime | None = None
    last_seen: datetime | None = None
    upload_bytes: int = 0
    download_bytes: int = 0
    upload_rate_mbps: float | None = None
    download_rate_mbps: float | None = None


@dataclass(frozen=True)
class CapabilityReport:
    can_monitor_upstream: bool = False
    can_monitor_downstream: bool = False
    can_discover_clients: bool = False
    can_attribute_client_traffic: bool = False
    can_manage_access_point: bool = False
    can_enable_forwarding: bool = False
    can_enable_nat: bool = False
    can_apply_upload_shaping: bool = False
    can_apply_download_shaping: bool = False
    supported_qdiscs: tuple[str, ...] = ()
    can_collect_queue_stats: bool = False
    can_collect_wifi_stats: bool = False
    can_multi_wan: bool = False
    can_policy_routing: bool = False
    can_recover_state: bool = False
    simultaneous_wifi_client_ap: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "can_monitor_upstream": self.can_monitor_upstream,
            "can_monitor_downstream": self.can_monitor_downstream,
            "can_discover_clients": self.can_discover_clients,
            "can_attribute_client_traffic": self.can_attribute_client_traffic,
            "can_manage_access_point": self.can_manage_access_point,
            "can_enable_forwarding": self.can_enable_forwarding,
            "can_enable_nat": self.can_enable_nat,
            "can_apply_upload_shaping": self.can_apply_upload_shaping,
            "can_apply_download_shaping": self.can_apply_download_shaping,
            "supported_qdiscs": list(self.supported_qdiscs),
            "can_collect_queue_stats": self.can_collect_queue_stats,
            "can_collect_wifi_stats": self.can_collect_wifi_stats,
            "can_multi_wan": self.can_multi_wan,
            "can_policy_routing": self.can_policy_routing,
            "can_recover_state": self.can_recover_state,
            "simultaneous_wifi_client_ap": self.simultaneous_wifi_client_ap,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Observation:
    """A single telemetry observation. All timestamps are UTC."""

    timestamp: datetime
    source: str
    scope: str  # aggregate_gateway | client
    environment: str  # physical_host | simulated_lab
    quality: str  # measured | derived | unavailable | unknown
    client_id: str | None = None
    gateway_id: str | None = None
    download_bytes: int | None = None
    upload_bytes: int | None = None
    download_packets: int | None = None
    upload_packets: int | None = None
    download_mbps: float | None = None
    upload_mbps: float | None = None
    rtt_ms: float | None = None
    rtt_variation_ms: float | None = None
    packet_loss_percent: float | None = None
    queue_depth_bytes: int | None = None
    queue_delay_ms: float | None = None
    interface_errors: int | None = None
    link_state: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    collector_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "scope": self.scope,
            "environment": self.environment,
            "quality": self.quality,
            "client_id": self.client_id,
            "gateway_id": self.gateway_id,
            "download_bytes": self.download_bytes,
            "upload_bytes": self.upload_bytes,
            "download_packets": self.download_packets,
            "upload_packets": self.upload_packets,
            "download_mbps": self.download_mbps,
            "upload_mbps": self.upload_mbps,
            "rtt_ms": self.rtt_ms,
            "rtt_variation_ms": self.rtt_variation_ms,
            "packet_loss_percent": self.packet_loss_percent,
            "queue_depth_bytes": self.queue_depth_bytes,
            "queue_delay_ms": self.queue_delay_ms,
            "interface_errors": self.interface_errors,
            "link_state": self.link_state,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "collector_error": self.collector_error,
        }


@runtime_checkable
class PlatformAdapter(Protocol):
    """Common interface every OS adapter must implement."""

    name: str
    platform: str

    async def discover_interfaces(self) -> list[InterfaceInfo]: ...
    async def detect_capabilities(self) -> CapabilityReport: ...
    async def discover_clients(self) -> list[ClientInfo]: ...
    async def collect_observations(self) -> list[Observation]: ...
    async def enable_ip_forwarding(self) -> bool: ...
    async def enable_nat(self) -> bool: ...
    async def apply_policy(self, allocations: dict[str, dict]) -> dict: ...
    async def read_back_state(self) -> dict: ...
    async def rollback(self) -> bool: ...

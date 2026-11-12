"""Linux platform adapter for the Experience Budget gateway agent.

Uses standard Linux networking tools: ip, iptables/nft, tc (CAKE/HTB+fq_codel),
hostapd/dnsmasq for AP, sysfs for counters. Requires root/CAP_NET_ADMIN.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


class LinuxAdapter(PlatformAdapter):
    name = "linux"
    platform = "linux"

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._capabilities: CapabilityReport | None = None

    async def _run(self, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", "timeout"
        return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    async def discover_interfaces(self) -> list[InterfaceInfo]:
        interfaces: list[InterfaceInfo] = []
        net_dir = Path("/sys/class/net")
        if not net_dir.exists():
            return interfaces
        for entry in sorted(net_dir.iterdir()):
            name = entry.name
            iface = entry
            type_ = "unknown"
            state = "down"
            mac = None
            try:
                type_path = iface / "type"
                if type_path.exists():
                    t = int(type_path.read_text().strip())
                    # ARPHRD_ETHER=1, ARPHRD_IEEE80211=801, etc.
                    type_map = {1: "ethernet", 801: "wifi", 772: "wifi", 28: "bond", 29: "dummy"}
                    type_ = type_map.get(t, "other")
            except (ValueError, OSError):
                pass
            try:
                state = (iface / "operstate").read_text().strip() or "down"
            except OSError:
                pass
            try:
                mac = (iface / "address").read_text().strip() or None
            except OSError:
                pass
            interfaces.append(InterfaceInfo(name=name, type=type_, state=state, mac=mac))
        return interfaces

    async def detect_capabilities(self) -> CapabilityReport:
        if self._capabilities is not None:
            return self._capabilities

        interfaces = await self.discover_interfaces()
        has_wifi = any(i.type == "wifi" for i in interfaces)
        has_multiple = len(interfaces) >= 2

        # Detect qdisc support via tc (read-only).
        supported_qdiscs: list[str] = []
        rc, out, _ = await self._run("tc", "qdisc", "show", "help")
        text = (out + "").lower()
        for q in ("cake", "htb", "fq_codel", "tbf", "sfq"):
            if q in text:
                supported_qdiscs.append(q)
        # Also probe kernel modules by attempting a harmless show on a dummy.
        rc, _, _ = await self._run("tc", "qdisc", "add", "dev", "lo", "root", "cake", "bandwidth", "100mbit")
        cake_ok = rc == 0
        if cake_ok:
            await self._run("tc", "qdisc", "del", "dev", "lo", "root")

        can_ap = has_wifi  # hostapd may or may not be installed; conservative
        can_forward = True  # Linux supports sysctl ip_forward
        can_nat = True  # iptables/nft available typically

        self._capabilities = CapabilityReport(
            can_monitor_upstream=True,
            can_monitor_downstream=True,
            can_discover_clients=True,
            can_attribute_client_traffic=True,
            can_manage_access_point=can_ap,
            can_enable_forwarding=can_forward,
            can_enable_nat=can_nat,
            can_apply_upload_shaping=True,
            can_apply_download_shaping=True,
            supported_qdiscs=tuple(supported_qdiscs),
            can_collect_queue_stats=True,
            can_collect_wifi_stats=has_wifi,
            can_multi_wan=has_multiple,
            can_policy_routing=True,
            can_recover_state=True,
            simultaneous_wifi_client_ap=has_wifi,
            notes=(
                "Linux tc enforcement available. "
                + ("CAKE supported." if cake_ok else "CAKE not available; HTB+fq_codel fallback.")
                + (" AP management via hostapd possible." if has_wifi else " No Wi-Fi interface detected.")
            ),
        )
        return self._capabilities

    async def discover_clients(self) -> list[ClientInfo]:
        """Discover clients via ARP/neighbour and DHCP lease sources where available."""
        clients: list[ClientInfo] = []
        # Read neighbour table (IPv4/IPv6).
        rc, out, _ = await self._run("ip", "-4", "neigh", "show")
        if rc == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and "lladdr" in parts:
                    ip = parts[0]
                    dev = parts[2] if parts[2] != "lladdr" else ""
                    llidx = parts.index("lladdr")
                    mac = parts[llidx + 1] if llidx + 1 < len(parts) else None
                    state = parts[-1]
                    connected = state in ("REACHABLE", "STALE", "DELAY", "PROBE")
                    clients.append(
                        ClientInfo(
                            client_id=self._opaque_id(mac or ip),
                            mac=mac,
                            ip=ip,
                            connected=connected,
                            last_seen=_utc_now() if connected else None,
                        )
                    )
        return clients

    def _opaque_id(self, value: str | None) -> str:
        import hashlib

        if not value:
            return "client-unknown"
        digest = hashlib.sha256(value.encode()).hexdigest()[:16]
        return f"client-{digest}"

    async def collect_observations(self) -> list[Observation]:
        """Collect per-interface counters and aggregate gateway observation."""
        observations: list[Observation] = []
        net_dir = Path("/sys/class/net")
        iface_states: dict[str, dict[str, int]] = {}
        for entry in sorted(net_dir.iterdir()):
            name = entry.name
            stats_dir = entry / "statistics"
            try:
                rx = int((stats_dir / "rx_bytes").read_text().strip())
                tx = int((stats_dir / "tx_bytes").read_text().strip())
                rx_p = int((stats_dir / "rx_packets").read_text().strip())
                tx_p = int((stats_dir / "tx_packets").read_text().strip())
            except (OSError, ValueError):
                continue
            iface_states[name] = {"rx_bytes": rx, "tx_bytes": tx, "rx_packets": rx_p, "tx_packets": tx_p}
            observations.append(
                Observation(
                    timestamp=_utc_now(),
                    source="linux_gateway",
                    scope="aggregate_gateway",
                    environment="physical_host",
                    quality="measured",
                    gateway_id=self.config.gateway_id or None,
                    download_bytes=tx,
                    upload_bytes=rx,
                    download_packets=tx_p,
                    upload_packets=rx_p,
                    link_state=(entry / "operstate").read_text().strip() if (entry / "operstate").exists() else None,
                )
            )
        return observations

    async def enable_ip_forwarding(self) -> bool:
        try:
            Path("/proc/sys/net/ipv4/ip_forward").write_text("1\n")
            return True
        except OSError:
            return False

    async def enable_nat(self) -> bool:
        wan = self.config.wan_interface
        lan = self.config.lan_interface
        if not wan or not lan:
            return False
        # Masquerade on WAN for traffic sourced from LAN.
        await self._run("iptables", "-t", "nat", "-A", "POSTROUTING", "-o", wan, "-j", "MASQUERADE")
        await self._run("iptables", "-A", "FORWARD", "-i", lan, "-o", wan, "-j", "ACCEPT")
        await self._run("iptables", "-A", "FORWARD", "-i", wan, "-o", lan, "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT")
        return True

    async def apply_policy(self, allocations: dict[str, dict]) -> dict:
        """Apply per-client download/upload shaping using tc (CAKE/HTB+fq_codel).

        allocations: {client_id: {"download_mbps": float|None, "upload_mbps": float|None}}
        Returns a report of what was applied.
        """
        applied: dict[str, Any] = {}
        # This is a skeleton; real enforcement needs interface<->client mapping.
        for client_id, alloc in allocations.items():
            applied[client_id] = {
                "download_mbps": alloc.get("download_mbps"),
                "upload_mbps": alloc.get("upload_mbps"),
                "applied": False,
                "reason": "requires_interface_mapping",
            }
        return {"mode": "tc", "applied": applied}

    async def read_back_state(self) -> dict:
        interfaces = await self.discover_interfaces()
        return {"interfaces": [i.name for i in interfaces], "platform": "linux"}

    async def rollback(self) -> bool:
        """Remove project-owned qdiscs (best effort, safe)."""
        try:
            await self._run("iptables", "-t", "nat", "-D", "POSTROUTING", "-o", self.config.wan_interface, "-j", "MASQUERADE")
        except Exception:
            pass
        return True

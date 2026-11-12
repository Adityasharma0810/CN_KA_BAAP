"""Real Linux hotspot client presence detection.

Detects wireless interfaces that the kernel reports in AP (hotspot) mode and
lists the devices seen on them through the kernel neighbour table.

Privacy boundary
----------------
Hardware addresses are transient collector state: they are mapped to
anonymous opaque client IDs in memory and are never returned, logged, or
persisted by this service. Only anonymous IDs and labels cross the boundary.

Honesty boundary
----------------
This is presence detection only. Per-client traffic counters for hotspot
clients would require root-level per-MAC accounting (CAP_NET_ADMIN), so no
per-client traffic observation is fabricated; hotspot clients are reported
with presence metadata only.
"""

from __future__ import annotations

import re
import subprocess
import threading
from datetime import datetime, timezone
from typing import Callable

from backend.app.services.client_registry import AnonymousClientRegistry

_IW_TIMEOUT_S = 3.0
_NEIGH_TIMEOUT_S = 3.0
_CACHE_TTL_S = 3.0
_MAX_HOTSPOT_CLIENTS = 64

_INTERFACE_RE = re.compile(r"^\s*Interface\s+(\S+)\s*$")
_TYPE_RE = re.compile(r"^\s*type\s+(\S+)\s*$")
_LLADDR_RE = re.compile(r"\blladdr\s+([0-9a-fA-F:]{17})\b")
_MAC_RE = re.compile(r"^[0-9a-fA-F:]{17}$")

CommandRunner = Callable[[list[str], float], "subprocess.CompletedProcess[str] | None"]


def _default_runner(command: list[str], timeout: float):
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _is_multicast_mac(mac: str) -> bool:
    """Return True for group addresses (I/G bit set or broadcast)."""

    try:
        first_octet = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return True
    return bool(first_octet & 0x01)


def _is_valid_unicast_mac(mac: str) -> bool:
    if not isinstance(mac, str) or _MAC_RE.fullmatch(mac) is None:
        return False
    normalized = mac.lower()
    if normalized == "ff:ff:ff:ff:ff:ff":
        return False
    return not _is_multicast_mac(normalized)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LinuxHotspotClientService:
    """Detect devices connected to a Linux-hosted hotspot, anonymously."""

    def __init__(
        self,
        *,
        registry: AnonymousClientRegistry | None = None,
        runner: CommandRunner | None = None,
        sys_class_net: str = "/sys/class/net",
        now: Callable[[], datetime] = utc_now,
    ):
        self.registry = registry or AnonymousClientRegistry()
        self._runner = runner or _default_runner
        self._sys_class_net = sys_class_net
        self._now = now
        self._address_to_client: dict[str, str] = {}
        self._lock = threading.Lock()
        self._cached: dict | None = None
        self._cached_at: datetime | None = None

    # -- detection ---------------------------------------------------------

    def _ap_interfaces(self) -> list[str]:
        """Return wireless interfaces the kernel reports in AP mode."""

        result = self._runner(["iw", "dev"], _IW_TIMEOUT_S)
        if result is None or result.returncode != 0:
            return []
        interfaces: list[str] = []
        current: str | None = None
        for line in (result.stdout or "").splitlines():
            interface = _INTERFACE_RE.fullmatch(line)
            if interface is not None:
                current = interface.group(1)
                continue
            mode = _TYPE_RE.fullmatch(line)
            if mode is not None and current is not None:
                if mode.group(1) == "AP":
                    interfaces.append(current)
                current = None
        return interfaces

    def _interface_mac(self, interface: str) -> str | None:
        """Return the interface's own hardware address, or None."""

        try:
            with open(f"{self._sys_class_net}/{interface}/address", "r") as handle:
                mac = handle.read().strip().lower()
        except OSError:
            return None
        return mac if _MAC_RE.fullmatch(mac) else None

    def _neighbour_macs(self, interface: str) -> list[str]:
        """Return unicast hardware addresses seen on one interface."""

        result = self._runner(
            ["ip", "neigh", "show", "dev", interface],
            _NEIGH_TIMEOUT_S,
        )
        if result is None or result.returncode != 0:
            return []
        addresses: list[str] = []
        for match in _LLADDR_RE.finditer(result.stdout or ""):
            mac = match.group(1).lower()
            if _is_valid_unicast_mac(mac):
                addresses.append(mac)
        return addresses

    # -- anonymous mapping -------------------------------------------------

    def _client_for_address(self, address: str, now: datetime) -> str:
        """Map one hardware address to a stable anonymous client ID.

        The mapping lives only inside this service for the process lifetime.
        The address itself is never placed on a public record.
        """

        with self._lock:
            client_id = self._address_to_client.get(address)
            if client_id is None:
                client_id = self.registry.register().client_id
                self._address_to_client[address] = client_id
            return client_id

    # -- collection --------------------------------------------------------

    def collect(self, *, refresh: bool = False) -> dict:
        """Return hotspot presence state, or an explicit unavailable state."""

        with self._lock:
            if not refresh and self._cached is not None and self._cached_at is not None:
                if (self._now() - self._cached_at).total_seconds() < _CACHE_TTL_S:
                    return self._cached

        result = self._collect_uncached()
        with self._lock:
            self._cached = result
            self._cached_at = self._now()
        return result

    def _collect_uncached(self) -> dict:
        now = self._now()
        interfaces = self._ap_interfaces()

        if not interfaces:
            return {
                "available": False,
                "source": "linux_hotspot",
                "environment": "physical_host",
                "clients": [],
                "message": "No wireless hotspot interface is present on this system.",
            }

        own_addresses = set()
        sighted: list[str] = []
        for interface in interfaces:
            own = self._interface_mac(interface)
            if own is not None:
                own_addresses.add(own)
            sighted.extend(self._neighbour_macs(interface))

        # De-duplicate while preserving order; drop this host's own addresses.
        seen: list[str] = []
        for address in sighted:
            if address in own_addresses or address in seen:
                continue
            seen.append(address)

        clients: list[dict] = []
        for address in seen[:_MAX_HOTSPOT_CLIENTS]:
            client_id = self._client_for_address(address, now)
            self.registry.mark_online(client_id, now=now)
            clients.append({"client_id": client_id})

        return {
            "available": True,
            "source": "linux_hotspot",
            "environment": "physical_host",
            "clients": clients,
            "message": None,
        }


hotspot_client_service = LinuxHotspotClientService()

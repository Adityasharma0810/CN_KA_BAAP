"""Genuine per-client accounting for the Linux namespace lab.

The lab topology has one gateway-side veth for each namespace client. Reading
only that endpoint's Linux counters gives independent client traffic without
counting both ends of a veth pair.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from backend.app.services.client_registry import AnonymousClientRegistry


_INTERFACE_PATTERN = re.compile(r"^veth-c([1-9][0-9]*)-br$")
_NAMESPACE_PATTERN = re.compile(r"^client([1-9][0-9]*)$")
_MIN_ELAPSED_SECONDS = 0.001


@dataclass(frozen=True)
class LabClientConfig:
    """Explicit mapping between a simulated client and lab infrastructure."""

    client_number: int
    client_id: str
    namespace_name: str
    gateway_interface: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_number, int) or isinstance(self.client_number, bool):
            raise ValueError("client_number must be an integer")
        if self.client_number < 1:
            raise ValueError("client_number must be positive")
        if not self.client_id:
            raise ValueError("client_id is required")
        namespace_match = _NAMESPACE_PATTERN.fullmatch(self.namespace_name)
        interface_match = _INTERFACE_PATTERN.fullmatch(self.gateway_interface)
        if namespace_match is None or interface_match is None:
            raise ValueError("invalid lab namespace or gateway interface")
        if int(namespace_match.group(1)) != self.client_number:
            raise ValueError("namespace does not match client_number")
        if int(interface_match.group(1)) != self.client_number:
            raise ValueError("gateway interface does not match client_number")


@dataclass(frozen=True)
class ClientCounterSnapshot:
    """One raw counter reading from one gateway-side veth."""

    received_bytes: int
    transmitted_bytes: int
    received_packets: int
    transmitted_packets: int
    observed_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "received_bytes",
            "transmitted_bytes",
            "received_packets",
            "transmitted_packets",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(timezone.utc))


@dataclass(frozen=True)
class RateResult:
    download_mbps: float | None
    upload_mbps: float | None
    valid: bool
    reason: str | None = None


def calculate_client_rates(
    previous: ClientCounterSnapshot | None,
    current: ClientCounterSnapshot,
    elapsed_seconds: float,
) -> RateResult:
    """Calculate client rates from gateway-veth counter deltas.

    Download is the veth transmit delta and upload is the veth receive delta.
    A missing baseline, reset, or unsafe elapsed interval produces unavailable
    rates rather than fabricated zero or negative values.
    """

    if not isinstance(elapsed_seconds, (int, float)) or isinstance(elapsed_seconds, bool):
        raise ValueError("elapsed_seconds must be numeric")
    if elapsed_seconds < _MIN_ELAPSED_SECONDS:
        raise ValueError("elapsed_seconds is too small")
    if previous is None:
        return RateResult(None, None, False, "no_baseline")

    deltas = {
        "download": current.transmitted_bytes - previous.transmitted_bytes,
        "upload": current.received_bytes - previous.received_bytes,
    }
    if any(delta < 0 for delta in deltas.values()):
        return RateResult(None, None, False, "counter_reset")

    factor = 8 / elapsed_seconds / 1_000_000
    return RateResult(
        download_mbps=round(deltas["download"] * factor, 6),
        upload_mbps=round(deltas["upload"] * factor, 6),
        valid=True,
    )


class SysfsCounterReader:
    """Read Linux interface counters without invoking shell commands."""

    def __init__(self, sys_class_net: Path = Path("/sys/class/net")):
        self.sys_class_net = Path(sys_class_net)

    def __call__(self, interface: str, observed_at: datetime | None = None) -> ClientCounterSnapshot:
        base = self.sys_class_net / interface / "statistics"
        timestamp = observed_at or datetime.now(timezone.utc)
        try:
            return ClientCounterSnapshot(
                received_bytes=int((base / "rx_bytes").read_text().strip()),
                transmitted_bytes=int((base / "tx_bytes").read_text().strip()),
                received_packets=int((base / "rx_packets").read_text().strip()),
                transmitted_packets=int((base / "tx_packets").read_text().strip()),
                observed_at=timestamp,
            )
        except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as error:
            raise RuntimeError(f"counter interface unavailable: {interface}") from error


@dataclass(frozen=True)
class ClientMeasurement:
    """Internal measurement result; only ``observation`` is client-facing."""

    client_id: str
    counter_source: str
    observation: TelemetryObservation
    rate_reason: str | None = None


class PerClientAccountingCollector:
    """Collect independent observations for an explicit client inventory."""

    def __init__(
        self,
        clients: Iterable[LabClientConfig],
        registry: AnonymousClientRegistry,
        *,
        reader: Callable[[str, datetime | None], ClientCounterSnapshot] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.clients = tuple(clients)
        self.registry = registry
        self.reader = reader or SysfsCounterReader()
        self.monotonic = monotonic
        self._previous: dict[str, ClientCounterSnapshot] = {}
        self._previous_time: dict[str, float] = {}
        self._validate_inventory()

    def collect(self, *, now: datetime | None = None) -> list[ClientMeasurement]:
        """Collect all clients; one unavailable interface does not stop others."""

        timestamp = self._utc_now(now)
        current_time = self.monotonic()
        results: list[ClientMeasurement] = []
        for client in self.clients:
            try:
                current = self.reader(client.gateway_interface, timestamp)
                previous = self._previous.get(client.client_id)
                previous_time = self._previous_time.get(client.client_id)
                elapsed = current_time - previous_time if previous_time is not None else None
                rates = (
                    calculate_client_rates(previous, current, elapsed)
                    if elapsed is not None
                    else RateResult(None, None, False, "no_baseline")
                )
                self._previous[client.client_id] = current
                self._previous_time[client.client_id] = current_time
                quality = ValueQuality.MEASURED if rates.valid else ValueQuality.UNAVAILABLE
                error = None if rates.valid else f"rate unavailable: {rates.reason}"
                observation = self._observation(
                    client,
                    current,
                    rates,
                    timestamp,
                    quality=quality,
                    collector_error=error,
                )
                self.registry.observe(observation)
                results.append(ClientMeasurement(client.client_id, client.gateway_interface, observation, rates.reason))
            except (RuntimeError, ValueError, OSError) as error:
                results.append(ClientMeasurement(
                    client.client_id,
                    client.gateway_interface,
                    self._unavailable_observation(client, timestamp, str(error)),
                    "interface_unavailable",
                ))
        return results

    def reset_baselines(self) -> None:
        """Forget rate baselines without changing registry state."""

        self._previous.clear()
        self._previous_time.clear()

    def _observation(
        self,
        client: LabClientConfig,
        current: ClientCounterSnapshot,
        rates: RateResult,
        timestamp: datetime,
        *,
        quality: ValueQuality,
        collector_error: str | None,
    ) -> TelemetryObservation:
        return TelemetryObservation(
            metadata={
                "observed_at": timestamp,
                "source": ObservationSource.LINUX_NAMESPACE_LAB,
                "scope": ObservationScope.CLIENT,
                "quality": quality,
                "environment": ObservationEnvironment.SIMULATED_LAB,
                "collector_error": collector_error,
                "client_id": client.client_id,
            },
            download_bytes=current.transmitted_bytes,
            upload_bytes=current.received_bytes,
            download_packets=current.transmitted_packets,
            upload_packets=current.received_packets,
            download_mbps=rates.download_mbps,
            upload_mbps=rates.upload_mbps,
        )

    def _unavailable_observation(
        self,
        client: LabClientConfig,
        timestamp: datetime,
        error: str,
    ) -> TelemetryObservation:
        return TelemetryObservation(
            metadata={
                "observed_at": timestamp,
                "source": ObservationSource.LINUX_NAMESPACE_LAB,
                "scope": ObservationScope.CLIENT,
                "quality": ValueQuality.UNAVAILABLE,
                "environment": ObservationEnvironment.SIMULATED_LAB,
                "collector_error": error[:500],
                "client_id": client.client_id,
            }
        )

    def _validate_inventory(self) -> None:
        if not self.clients:
            raise ValueError("at least one lab client is required")
        ids = [client.client_id for client in self.clients]
        numbers = [client.client_number for client in self.clients]
        interfaces = [client.gateway_interface for client in self.clients]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate anonymous client IDs")
        if len(set(numbers)) != len(numbers):
            raise ValueError("duplicate client numbers")
        if len(set(interfaces)) != len(interfaces):
            raise ValueError("duplicate gateway interfaces")
        for client in self.clients:
            self.registry.get(client.client_id)

    @staticmethod
    def _utc_now(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)


def build_lab_inventory(
    registry: AnonymousClientRegistry,
    *,
    client_numbers: Iterable[int] = (1, 2, 3),
) -> tuple[LabClientConfig, ...]:
    """Build explicit simulated-client mappings for the existing lab topology."""

    numbers = tuple(client_numbers)
    if not numbers or any(isinstance(number, bool) or number < 1 for number in numbers):
        raise ValueError("client_numbers must contain positive integers")
    if len(set(numbers)) != len(numbers):
        raise ValueError("duplicate client numbers")

    registered = registry.list_clients()
    while len(registered) < len(numbers):
        registry.register()
        registered = registry.list_clients()
    # Labels are sorted; registration order is preserved by labels.
    registered_by_label = sorted(registered, key=lambda item: item.display_label)
    return tuple(
        LabClientConfig(
            client_number=number,
            client_id=registered_by_label[index].client_id,
            namespace_name=f"client{number}",
            gateway_interface=f"veth-c{number}-br",
        )
        for index, number in enumerate(numbers)
    )

"""Genuine per-client accounting for the Linux namespace lab.

The lab topology has one gateway-side veth for each namespace client. Reading
only that endpoint's Linux counters gives independent client traffic without
counting both ends of a veth pair.
"""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

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
_DISPLAY_LABEL_PATTERN = re.compile(r"^Client ([0-9]{2,})$")
_MIN_ELAPSED_SECONDS = 0.001
DEFAULT_CLIENT_COUNT = 3
MAX_LAB_CLIENTS = 99
MAX_INTERFACE_NAME_LENGTH = 15


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
        if self.client_number > MAX_LAB_CLIENTS:
            raise ValueError(f"client_number must not exceed {MAX_LAB_CLIENTS}")
        if not isinstance(self.client_id, str) or not self.client_id:
            raise ValueError("client_id is required")
        namespace_match = _NAMESPACE_PATTERN.fullmatch(self.namespace_name)
        interface_match = _INTERFACE_PATTERN.fullmatch(self.gateway_interface)
        if namespace_match is None or interface_match is None:
            raise ValueError("invalid lab namespace or gateway interface")
        if len(self.gateway_interface) > MAX_INTERFACE_NAME_LENGTH:
            raise ValueError("gateway interface name is too long")
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
        if not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a datetime")
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
    elapsed = float(elapsed_seconds)
    if not math.isfinite(elapsed):
        raise ValueError("elapsed_seconds must be finite")
    if elapsed < _MIN_ELAPSED_SECONDS:
        raise ValueError("elapsed_seconds is too small")
    if previous is None:
        return RateResult(None, None, False, "no_baseline")

    deltas = {
        "download": current.transmitted_bytes - previous.transmitted_bytes,
        "upload": current.received_bytes - previous.received_bytes,
    }
    if any(delta < 0 for delta in deltas.values()):
        return RateResult(None, None, False, "counter_reset")

    factor = 8 / elapsed / 1_000_000
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
                if previous is None or elapsed is None:
                    rates = RateResult(None, None, False, "no_baseline")
                else:
                    try:
                        rates = calculate_client_rates(previous, current, elapsed)
                    except ValueError:
                        # A monotonic clock that stalls or moves backwards cannot
                        # produce a safe interval. Rebase instead of reusing an
                        # old baseline on the next sample.
                        rates = RateResult(None, None, False, "invalid_elapsed")
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


def _validate_client_numbers(client_numbers: Iterable[int]) -> tuple[int, ...]:
    try:
        numbers = tuple(client_numbers)
    except TypeError as error:
        raise ValueError("client_numbers must be an iterable of integers") from error
    if not numbers:
        raise ValueError("client_numbers must contain positive integers")
    for number in numbers:
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError("client_numbers must contain positive integers")
        if number > MAX_LAB_CLIENTS:
            raise ValueError(f"client_numbers must not exceed {MAX_LAB_CLIENTS}")
    if len(set(numbers)) != len(numbers):
        raise ValueError("duplicate client numbers")
    return numbers


def _label_number(display_label: str) -> int:
    match = _DISPLAY_LABEL_PATTERN.fullmatch(display_label)
    if match is None:
        raise ValueError("invalid anonymous client display label")
    return int(match.group(1))


def build_lab_inventory(
    registry: AnonymousClientRegistry,
    *,
    client_numbers: Iterable[int] = tuple(range(1, DEFAULT_CLIENT_COUNT + 1)),
) -> tuple[LabClientConfig, ...]:
    """Build explicit simulated-client mappings for the existing lab topology.

    The registry label number is the lab client number. Registering up to the
    largest requested number keeps existing labels stable when the inventory is
    grown from three to five clients.
    """

    numbers = _validate_client_numbers(client_numbers)
    required = max(numbers)
    registered = registry.list_clients()
    while len(registered) < required:
        registry.register()
        registered = registry.list_clients()
    # Sort numerically rather than lexicographically so labels above 99 do not
    # reorder the inventory.
    registered_by_number = sorted(registered, key=lambda item: _label_number(item.display_label))
    return tuple(
        LabClientConfig(
            client_number=number,
            client_id=registered_by_number[number - 1].client_id,
            namespace_name=f"client{number}",
            gateway_interface=f"veth-c{number}-br",
        )
        for number in numbers
    )


def client_numbers_from_environment(
    environ: Mapping[str, str] | None = None,
) -> tuple[int, ...]:
    """Read ``EB_LAB_CLIENTS`` as a client count, defaulting to three."""

    values = os.environ if environ is None else environ
    raw = values.get("EB_LAB_CLIENTS", "").strip()
    if not raw:
        count = DEFAULT_CLIENT_COUNT
    else:
        if re.fullmatch(r"[1-9][0-9]*", raw) is None:
            raise ValueError("EB_LAB_CLIENTS must be a positive integer")
        count = int(raw)
    return _validate_client_numbers(range(1, count + 1))

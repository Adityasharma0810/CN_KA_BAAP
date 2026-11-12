"""Application service for optional Linux namespace-lab observations.

Anonymous lab clients are registered lazily: the registry and accounting
collector stay empty until a configured lab counter interface actually
exists, so an unavailable lab never produces phantom "Client 01..N" entries
with no telemetry.
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from gateway.accounting import (
    LabClientConfig,
    PerClientAccountingCollector,
    SysfsCounterReader,
    build_lab_inventory,
    client_numbers_from_environment,
)
from backend.app.services.client_registry import AnonymousClientRegistry


class LabAccountingService:
    """Own the runtime registry and accounting collector for the Linux lab."""

    def __init__(self, sys_class_net: Path = Path("/sys/class/net")):
        self.registry = AnonymousClientRegistry()
        self.inventory: tuple[LabClientConfig, ...] = ()
        self._sys_class_net = Path(sys_class_net)
        self.collector: PerClientAccountingCollector | None = None
        self._lock = Lock()

    def is_available(self) -> bool:
        """Return whether any configured lab counter interface currently exists."""

        return any(
            (self._sys_class_net / f"veth-c{number}-br").exists()
            for number in client_numbers_from_environment()
        )

    def _ensure_inventory(self) -> None:
        """Register lab clients only once a lab interface actually exists."""

        if self.collector is not None or not self.is_available():
            return
        with self._lock:
            if self.collector is not None:
                return
            reader = SysfsCounterReader(self._sys_class_net)
            self.inventory = build_lab_inventory(
                self.registry,
                client_numbers=client_numbers_from_environment(),
            )
            # Keep the production collector free of shell commands and make
            # the lab root injectable for integration tests.
            self.collector = PerClientAccountingCollector(
                self.inventory,
                self.registry,
                reader=reader,
            )

    def configure_persisted_clients(
        self, persisted_client_ids: dict[int, str]
    ) -> None:
        """Restore stable anonymous IDs from canonical storage before ingest.

        The registry is only populated when the lab is actually available; an
        unavailable lab leaves the registry empty instead of registering
        clients that can never produce measurements.
        """

        with self._lock:
            self.registry.reset()
            self.inventory = ()
            self.collector = None
            if not self.is_available():
                return
            numbers = client_numbers_from_environment()
            for number in numbers:
                self.registry.register(
                    client_id=persisted_client_ids.get(number)
                )
            self.inventory = build_lab_inventory(
                self.registry,
                client_numbers=numbers,
            )
            self.collector = PerClientAccountingCollector(
                self.inventory,
                self.registry,
                reader=SysfsCounterReader(self._sys_class_net),
            )

    def collect(self) -> dict:
        """Return genuine client observations, or an explicit unavailable state."""

        self._ensure_inventory()

        if self.collector is None or not self.is_available():
            return {
                "available": False,
                "source": "linux_namespace_lab",
                "environment": "simulated_lab",
                "scope": "client",
                "clients": [],
                "message": "Linux namespace lab interfaces are unavailable.",
            }

        with self._lock:
            measurements = self.collector.collect()

        return {
            "available": True,
            "source": "linux_namespace_lab",
            "environment": "simulated_lab",
            "scope": "client",
            "clients": [
                {
                    "client_id": measurement.client_id,
                    "observation": measurement.observation.model_dump(mode="json"),
                    "rate_reason": measurement.rate_reason,
                }
                for measurement in measurements
            ],
        }


lab_accounting_service = LabAccountingService()

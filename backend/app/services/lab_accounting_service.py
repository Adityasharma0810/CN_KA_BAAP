"""Application service for optional Linux namespace-lab observations."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from gateway.accounting import (
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
        self.inventory = build_lab_inventory(
            self.registry,
            client_numbers=client_numbers_from_environment(),
        )
        self.collector = PerClientAccountingCollector(
            self.inventory,
            self.registry,
            # Keep the production collector free of shell commands and make
            # the lab root injectable for integration tests.
            reader=SysfsCounterReader(sys_class_net),
        )
        self._lock = Lock()

    def is_available(self) -> bool:
        """Return whether any configured lab counter interface currently exists."""

        return any(
            (Path(self.collector.reader.sys_class_net) / client.gateway_interface).exists()
            for client in self.inventory
        )

    def configure_persisted_clients(
        self, persisted_client_ids: dict[int, str]
    ) -> None:
        """Restore stable anonymous IDs from canonical storage before ingest."""

        with self._lock:
            self.registry.reset()
            numbers = client_numbers_from_environment()
            for number in numbers:
                self.registry.register(
                    client_id=persisted_client_ids.get(number)
                )
            reader = self.collector.reader
            self.inventory = build_lab_inventory(
                self.registry,
                client_numbers=numbers,
            )
            self.collector = PerClientAccountingCollector(
                self.inventory,
                self.registry,
                reader=reader,
            )

    def collect(self) -> dict:
        """Return genuine client observations, or an explicit unavailable state."""

        if not self.is_available():
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

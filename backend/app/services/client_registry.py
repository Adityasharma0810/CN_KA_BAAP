"""Runtime-only anonymous client registry.

The registry deliberately has no persistence dependency. Address associations
are transient collector state and are never included in public representations.
A process restart or explicit reset creates a new anonymous session.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from backend.app.models.schemas import ClientId, TelemetryObservation


class ClientStatus(str, Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"


class AnonymousClient(BaseModel):
    """Public, privacy-safe client representation."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    client_id: ClientId
    display_label: str = Field(pattern=r"^Client [0-9]{2,}$")
    status: ClientStatus
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    stale: bool = False


class _ClientRecord:
    __slots__ = (
        "client_id",
        "display_label",
        "first_seen_at",
        "last_seen_at",
        "explicit_offline",
    )

    def __init__(self, client_id: str, display_label: str):
        self.client_id = client_id
        self.display_label = display_label
        self.first_seen_at: datetime | None = None
        self.last_seen_at: datetime | None = None
        self.explicit_offline = False


class AnonymousClientRegistry:
    """Thread-safe session registry for anonymous clients.

    ``online_after`` controls how long a valid observation keeps a client
    online. ``offline_after`` controls when an observed client becomes offline.
    A never-observed client remains unknown. Address keys are accepted only for
    transient association and cannot be returned or serialized by this class.
    """

    def __init__(
        self,
        *,
        online_after: timedelta = timedelta(seconds=30),
        offline_after: timedelta = timedelta(minutes=5),
        association_after: timedelta | None = None,
        token_bytes: int = 16,
    ):
        if online_after <= timedelta(0):
            raise ValueError("online_after must be positive")
        if offline_after < online_after:
            raise ValueError("offline_after must not precede online_after")
        if association_after is not None and association_after <= timedelta(0):
            raise ValueError("association_after must be positive")
        if token_bytes < 16:
            raise ValueError("token_bytes must provide collision-resistant IDs")

        self.online_after = online_after
        self.offline_after = offline_after
        self.association_after = association_after or offline_after
        self._token_bytes = token_bytes
        self._clients: dict[str, _ClientRecord] = {}
        self._address_to_client: dict[str, tuple[str, datetime]] = {}
        self._next_label = 1
        self._lock = threading.RLock()

    def register(self, *, client_id: str | None = None) -> AnonymousClient:
        """Register a client, optionally restoring its persisted opaque ID."""

        with self._lock:
            if client_id is None:
                while True:
                    client_id = f"client-{secrets.token_hex(self._token_bytes)}"
                    if client_id not in self._clients:
                        break
            else:
                try:
                    client_id = TypeAdapter(ClientId).validate_python(client_id)
                except (TypeError, ValueError) as error:
                    raise ValueError("invalid anonymous client ID") from error
                if client_id in self._clients:
                    raise ValueError("anonymous client ID is already registered")
            label = f"Client {self._next_label:02d}"
            self._next_label += 1
            self._clients[client_id] = _ClientRecord(client_id, label)
            return self._public_record(self._clients[client_id], None)

    def get(self, client_id: str, *, now: datetime | None = None) -> AnonymousClient:
        """Return one public client record after validating its anonymous ID."""

        with self._lock:
            record = self._require_record(client_id)
            return self._public_record(record, self._coerce_utc(now))

    def list_clients(self, *, now: datetime | None = None) -> list[AnonymousClient]:
        """Return public records in display-label order."""

        with self._lock:
            current = self._coerce_utc(now)
            records = sorted(self._clients.values(), key=lambda item: item.display_label)
            return [self._public_record(record, current) for record in records]

    def observe(
        self,
        observation: TelemetryObservation,
        *,
        now: datetime | None = None,
    ) -> AnonymousClient:
        """Update last-seen state from a valid client-scoped observation."""

        client_id = observation.metadata.client_id
        if client_id is None:
            raise ValueError("client observation must contain an anonymous client_id")
        if observation.metadata.scope != "client":
            raise ValueError("only client-scoped observations update a client")
        observed_at = self._coerce_utc(now or observation.metadata.observed_at)

        with self._lock:
            record = self._require_record(client_id)
            if record.last_seen_at is not None and observed_at < record.last_seen_at:
                raise ValueError("observation timestamp precedes last seen timestamp")
            if record.first_seen_at is None:
                record.first_seen_at = observed_at
            record.last_seen_at = observed_at
            record.explicit_offline = False
            return self._public_record(record, observed_at)

    def mark_offline(self, client_id: str, *, now: datetime | None = None) -> AnonymousClient:
        """Mark a known client offline without deleting its anonymous record."""

        with self._lock:
            record = self._require_record(client_id)
            record.explicit_offline = True
            return self._public_record(record, self._coerce_utc(now))

    def mark_online(self, client_id: str, *, now: datetime | None = None) -> AnonymousClient:
        """Record a presence sighting without requiring a telemetry observation.

        Presence collectors (for example hotspot client detection) can prove a
        device is reachable but have no per-client traffic measurement to
        report. Marking a sighting keeps first/last-seen state honest without
        fabricating an observation.
        """

        observed_at = self._coerce_utc(now)
        with self._lock:
            record = self._require_record(client_id)
            if record.first_seen_at is None:
                record.first_seen_at = observed_at
            if record.last_seen_at is None or observed_at >= record.last_seen_at:
                record.last_seen_at = observed_at
            record.explicit_offline = False
            return self._public_record(record, observed_at)

    def associate_address(
        self,
        client_id: str,
        address: str,
        *,
        now: datetime | None = None,
    ) -> None:
        """Associate a transient collector address with one client only.

        The address is deliberately not validated into a public identity model,
        stored on a client record, returned, or serialized. A collision is
        rejected instead of silently moving an address between clients.
        """

        if not isinstance(address, str) or not address.strip() or len(address) > 128:
            raise ValueError("address must be a non-empty bounded string")
        current = self._coerce_utc(now)
        with self._lock:
            self._require_record(client_id)
            existing = self._address_to_client.get(address)
            if existing is not None and existing[0] != client_id:
                raise ValueError("address is already associated with another client")
            self._address_to_client[address] = (client_id, current)

    def lookup_address(self, address: str, *, now: datetime | None = None) -> str | None:
        """Resolve a transient address internally, or return ``None`` if absent."""

        current = self._coerce_utc(now)
        with self._lock:
            association = self._address_to_client.get(address)
            if association is None:
                return None
            client_id, associated_at = association
            if current - associated_at > self.association_after:
                del self._address_to_client[address]
                return None
            return client_id

    def remove(self, client_id: str) -> None:
        """Remove one client and all of its transient associations."""

        with self._lock:
            self._require_record(client_id)
            del self._clients[client_id]
            self._address_to_client = {
                address: association
                for address, association in self._address_to_client.items()
                if association[0] != client_id
            }

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        """Remove expired address mappings while retaining client records."""

        current = self._coerce_utc(now)
        with self._lock:
            expired = [
                address
                for address, (_, associated_at) in self._address_to_client.items()
                if current - associated_at > self.association_after
            ]
            for address in expired:
                del self._address_to_client[address]
            return len(expired)

    def reset(self) -> None:
        """Start a fresh runtime session without touching external application data."""

        with self._lock:
            self._clients.clear()
            self._address_to_client.clear()
            self._next_label = 1

    def public_snapshot(self) -> list[dict[str, Any]]:
        """Return JSON-safe public data; never includes transient mappings."""

        return [client.model_dump(mode="json") for client in self.list_clients()]

    def _require_record(self, client_id: str) -> _ClientRecord:
        try:
            TypeAdapter(ClientId).validate_python(client_id)
        except (TypeError, ValueError):
            raise ValueError("invalid anonymous client ID")
        try:
            return self._clients[client_id]
        except KeyError as error:
            raise KeyError("unknown anonymous client ID") from error

    def _public_record(self, record: _ClientRecord, now: datetime | None) -> AnonymousClient:
        status, stale = self._status(record, now)
        return AnonymousClient(
            client_id=record.client_id,
            display_label=record.display_label,
            status=status,
            first_seen_at=record.first_seen_at,
            last_seen_at=record.last_seen_at,
            stale=stale,
        )

    def _status(self, record: _ClientRecord, now: datetime | None) -> tuple[ClientStatus, bool]:
        if record.last_seen_at is None:
            return ClientStatus.UNKNOWN, False
        if record.explicit_offline:
            return ClientStatus.OFFLINE, True
        age = (now or record.last_seen_at) - record.last_seen_at
        if age <= self.online_after:
            return ClientStatus.ONLINE, False
        return ClientStatus.OFFLINE, age > self.offline_after

    @staticmethod
    def _coerce_utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)

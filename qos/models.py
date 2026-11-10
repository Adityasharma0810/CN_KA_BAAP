"""Typed, privacy-safe contracts for Linux traffic enforcement.

The models in this module contain no IP addresses, MAC addresses, hostnames,
or packet payloads. Interface names are kept internal to the enforcer and are
never serialized by :meth:`EnforcementStatus.to_public_dict`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Mapping


CLIENT_ID_PATTERN = re.compile(r"^client-[a-z0-9]{8,32}$")
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")
SLOT_MIN = 1
SLOT_MAX = 99
RATE_MIN_MBPS = 0.1
RATE_MAX_MBPS = 100_000.0
BURST_MIN_KB = 4
BURST_MAX_KB = 1_000_000


class EnforcementMode(str, Enum):
    """A supported Linux queueing discipline architecture."""

    CAKE = "cake"
    HTB_FQ_CODEL = "htb_fq_codel"
    NONE = "none"


class RequestedMode(str, Enum):
    """Controller/environment request before capability negotiation."""

    AUTO = "auto"
    CAKE = "cake"
    HTB_FQ_CODEL = "htb_fq_codel"


class EnforcementState(str, Enum):
    """Public lifecycle state of the enforcement layer."""

    UNCONFIGURED = "unconfigured"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    ROLLED_BACK = "rolled_back"
    REMOVED = "removed"


class Direction(str, Enum):
    DOWNLOAD = "download"
    UPLOAD = "upload"


class EnforcementError(RuntimeError):
    """Base class for safe enforcement failures."""

    code = "enforcement_failed"


class EnforcementValidationError(EnforcementError):
    code = "invalid_enforcement_plan"


class CapabilityError(EnforcementError):
    code = "enforcement_unsupported"


class UnsafeResourceError(EnforcementError):
    code = "resource_not_owned"


class CommandError(EnforcementError):
    code = "tc_command_failed"


class CommandTimeoutError(CommandError):
    code = "tc_command_timeout"


class VerificationError(EnforcementError):
    code = "tc_readback_mismatch"


class RollbackError(EnforcementError):
    code = "rollback_failed"


def _finite_rate(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EnforcementValidationError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise EnforcementValidationError(f"{name} must be finite")
    if number < RATE_MIN_MBPS or number > RATE_MAX_MBPS:
        raise EnforcementValidationError(
            f"{name} must be between {RATE_MIN_MBPS} and {RATE_MAX_MBPS} Mbit/s"
        )
    return number


def _burst(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EnforcementValidationError(f"{name} must be an integer")
    if value < BURST_MIN_KB or value > BURST_MAX_KB:
        raise EnforcementValidationError(
            f"{name} must be between {BURST_MIN_KB} and {BURST_MAX_KB} KiB"
        )
    return value


def burst_kb_for(rate_mbps: float) -> int:
    """Return a documented, bounded burst for a shaped rate.

    The formula is intentionally simple and deterministic so the configured
    burst can be reproduced from the rate in tests and experiment manifests.
    """

    rate = _finite_rate(rate_mbps, "rate_mbps")
    return max(32, min(64_000, int(math.ceil(rate * 2 + 64))))


@dataclass(frozen=True)
class LabLink:
    """Runtime mapping between an anonymous client and lab-owned interfaces.

    ``download_interface`` is the gateway-side veth. ``upload_interface`` is the
    same veth viewed at ingress. ``ifb_interface`` is the project-owned IFB
    device used only when upload shaping is required.
    """

    client_id: str
    slot: int
    download_interface: str
    upload_interface: str
    ifb_interface: str

    def __post_init__(self) -> None:
        if CLIENT_ID_PATTERN.fullmatch(self.client_id) is None:
            raise EnforcementValidationError("invalid anonymous client ID")
        if (
            isinstance(self.slot, bool)
            or not isinstance(self.slot, int)
            or not SLOT_MIN <= self.slot <= SLOT_MAX
        ):
            raise EnforcementValidationError("invalid lab slot")
        for name in ("download_interface", "upload_interface", "ifb_interface"):
            value = getattr(self, name)
            if not isinstance(value, str) or INTERFACE_PATTERN.fullmatch(value) is None:
                raise EnforcementValidationError(f"invalid {name}")
        if self.ifb_interface == self.download_interface:
            raise EnforcementValidationError("IFB interface must be distinct")
        if self.upload_interface != self.download_interface:
            raise EnforcementValidationError(
                "upload and download must use the same gateway-side veth"
            )

    @classmethod
    def for_slot(
        cls,
        *,
        client_id: str,
        slot: int,
        ifb_prefix: str = "ifb-eb-",
    ) -> "LabLink":
        if not isinstance(ifb_prefix, str) or INTERFACE_PATTERN.fullmatch(
            ifb_prefix + str(slot)
        ) is None:
            raise EnforcementValidationError("invalid IFB prefix")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 1:
            raise EnforcementValidationError("invalid lab slot")
        return cls(
            client_id=client_id,
            slot=slot,
            download_interface=f"veth-c{slot}-br",
            upload_interface=f"veth-c{slot}-br",
            ifb_interface=f"{ifb_prefix}{slot}",
        )


@dataclass(frozen=True)
class ClientAllocation:
    """A validated per-client rate request in Mbit/s."""

    client_id: str
    download_mbps: float | None = None
    upload_mbps: float | None = None
    burst_kb: int | None = None

    def __post_init__(self) -> None:
        if CLIENT_ID_PATTERN.fullmatch(self.client_id) is None:
            raise EnforcementValidationError("invalid anonymous client ID")
        if self.download_mbps is None and self.upload_mbps is None:
            raise EnforcementValidationError(
                "allocation must request at least one direction"
            )
        if self.download_mbps is not None:
            object.__setattr__(
                self,
                "download_mbps",
                _finite_rate(self.download_mbps, "download_mbps"),
            )
        if self.upload_mbps is not None:
            object.__setattr__(
                self,
                "upload_mbps",
                _finite_rate(self.upload_mbps, "upload_mbps"),
            )
        if self.burst_kb is not None:
            object.__setattr__(
                self, "burst_kb", _burst(self.burst_kb, "burst_kb")
            )

    def rate_for(self, direction: Direction) -> float | None:
        return (
            self.download_mbps
            if direction == Direction.DOWNLOAD
            else self.upload_mbps
        )

    def burst_for(self, direction: Direction) -> int:
        if self.burst_kb is not None:
            return self.burst_kb
        rate = self.rate_for(direction)
        return burst_kb_for(rate) if rate is not None else BURST_MIN_KB


@dataclass(frozen=True)
class AllocationPlan:
    """A capacity-bounded set of per-client allocations."""

    capacity_mbps: float
    allocations: tuple[ClientAllocation, ...] = field(default_factory=tuple)
    requested_mode: RequestedMode = RequestedMode.AUTO

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capacity_mbps",
            _finite_rate(self.capacity_mbps, "capacity_mbps"),
        )
        try:
            requested = RequestedMode(self.requested_mode)
        except (TypeError, ValueError) as error:
            raise EnforcementValidationError("invalid requested mode") from error
        object.__setattr__(self, "requested_mode", requested)
        allocations = tuple(self.allocations)
        object.__setattr__(self, "allocations", allocations)

        client_ids = [item.client_id for item in allocations]
        if len(set(client_ids)) != len(client_ids):
            raise EnforcementValidationError("duplicate client allocation")
        for direction in (Direction.DOWNLOAD, Direction.UPLOAD):
            rates = [
                item.rate_for(direction)
                for item in allocations
                if item.rate_for(direction) is not None
            ]
            if sum(rates) > self.capacity_mbps + 1e-9:
                raise EnforcementValidationError(
                    f"{direction.value} allocations exceed available capacity"
                )

    @classmethod
    def from_mapping(
        cls,
        *,
        capacity_mbps: float,
        download_mbps: Mapping[str, float | None],
        upload_mbps: Mapping[str, float | None] | None = None,
        requested_mode: RequestedMode | str = RequestedMode.AUTO,
        burst_kb: int | None = None,
    ) -> "AllocationPlan":
        uploads = upload_mbps or {}
        client_ids = sorted(set(download_mbps) | set(uploads))
        allocations = tuple(
            ClientAllocation(
                client_id=client_id,
                download_mbps=download_mbps.get(client_id),
                upload_mbps=uploads.get(client_id),
                burst_kb=burst_kb,
            )
            for client_id in client_ids
            if download_mbps.get(client_id) is not None
            or uploads.get(client_id) is not None
        )
        return cls(
            capacity_mbps=capacity_mbps,
            allocations=allocations,
            requested_mode=RequestedMode(requested_mode),
        )

    def by_client(self) -> dict[str, ClientAllocation]:
        return {item.client_id: item for item in self.allocations}


@dataclass(frozen=True)
class CapabilityReport:
    """Detected kernel and tool capabilities."""

    checked_at: datetime
    kernel_release: str
    tc_version: str | None
    cake: bool
    htb: bool
    fq_codel: bool
    ifb: bool
    matchall: bool
    mirred: bool
    selected_mode: EnforcementMode
    reason: str

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise EnforcementValidationError("checked_at must include a timezone")
        object.__setattr__(
            self,
            "checked_at",
            self.checked_at.astimezone(timezone.utc),
        )
        if self.selected_mode not in {
            EnforcementMode.CAKE,
            EnforcementMode.HTB_FQ_CODEL,
            EnforcementMode.NONE,
        }:
            raise EnforcementValidationError("invalid selected mode")

    def supports(self, mode: EnforcementMode) -> bool:
        if mode == EnforcementMode.CAKE:
            return self.cake and self.tc_version is not None
        if mode == EnforcementMode.HTB_FQ_CODEL:
            return (
                self.htb
                and self.fq_codel
                and self.tc_version is not None
            )
        return False

    def to_public_dict(self) -> dict[str, object]:
        return {
            "checked_at": self.checked_at.isoformat(),
            "kernel_release": self.kernel_release,
            "tc_available": self.tc_version is not None,
            "cake_supported": self.cake,
            "htb_supported": self.htb,
            "fq_codel_supported": self.fq_codel,
            "ifb_supported": self.ifb,
            "matchall_supported": self.matchall,
            "mirred_supported": self.mirred,
            "selected_mode": self.selected_mode.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QdiscReadback:
    """Parsed, non-identifying view of one interface's qdisc state."""

    interface: str
    root_kind: str | None
    root_rate_mbps: float | None
    leaf_kinds: tuple[str, ...]
    ingress_present: bool
    redirect_targets: tuple[str, ...]


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    mode: EnforcementMode
    errors: tuple[str, ...]
    readback: tuple[QdiscReadback, ...]

    def require_ok(self) -> None:
        if not self.ok:
            raise VerificationError(
                "kernel traffic-control readback did not match the request"
            )


@dataclass(frozen=True)
class EnforcementStatus:
    """Auditable enforcement status with no raw network identifiers."""

    state: EnforcementState
    mode: EnforcementMode
    requested_mode: RequestedMode
    reason: str
    applied_at: datetime | None
    verified: bool
    client_count: int
    rollback_ok: bool | None = None
    rolled_back_at: datetime | None = None
    last_error: str | None = None

    def to_public_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "mode": self.mode.value,
            "requested_mode": self.requested_mode.value,
            "reason": self.reason,
            "applied_at": (
                self.applied_at.isoformat() if self.applied_at else None
            ),
            "verified": self.verified,
            "client_count": self.client_count,
            "rollback_ok": self.rollback_ok,
            "rolled_back_at": (
                self.rolled_back_at.isoformat()
                if self.rolled_back_at
                else None
            ),
            "last_error": self.last_error,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def links_for_clients(
    client_ids_by_slot: Mapping[int, str],
    *,
    ifb_prefix: str = "ifb-eb-",
) -> tuple[LabLink, ...]:
    links = tuple(
        LabLink.for_slot(
            client_id=client_id,
            slot=slot,
            ifb_prefix=ifb_prefix,
        )
        for slot, client_id in sorted(client_ids_by_slot.items())
    )
    if len({link.client_id for link in links}) != len(links):
        raise EnforcementValidationError("duplicate client ID in lab links")
    if len({link.slot for link in links}) != len(links):
        raise EnforcementValidationError("duplicate lab slot")
    return links


def validate_link_coverage(
    plan: AllocationPlan,
    links: Iterable[LabLink],
) -> dict[str, LabLink]:
    """Require exactly one lab link per allocated client."""

    materialized = tuple(links)
    by_client = {link.client_id: link for link in materialized}
    if len(by_client) != len(materialized):
        raise EnforcementValidationError("duplicate lab link")
    plan_ids = set(plan.by_client())
    missing = plan_ids - set(by_client)
    if missing:
        raise EnforcementValidationError("allocation has no lab link")
    return {client_id: by_client[client_id] for client_id in plan_ids}

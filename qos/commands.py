"""Pure command construction for CAKE and HTB + fq_codel enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from qos.models import (
    ClientAllocation,
    Direction,
    EnforcementMode,
    EnforcementValidationError,
    LabLink,
    burst_kb_for,
)


Command = tuple[str, ...]


@dataclass(frozen=True)
class CommandSet:
    """An ordered, idempotent set of commands for one direction."""

    mode: EnforcementMode
    direction: Direction
    commands: tuple[Command, ...]
    interface: str
    ifb_interface: str | None = None

    def __iter__(self):
        return iter(self.commands)


def _rate(rate_mbps: float) -> str:
    # tc accepts decimal Mbit/s and rounds internally; keep one decimal place.
    return f"{rate_mbps:g}mbit"


def _burst(burst_kb: int) -> str:
    return f"{burst_kb}kb"


def _cake_commands(interface: str, rate_mbps: float) -> list[Command]:
    return [
        (
            "tc",
            "qdisc",
            "replace",
            "dev",
            interface,
            "root",
            "cake",
            "bandwidth",
            _rate(rate_mbps),
            "besteffort",
        )
    ]


def _htb_commands(
    interface: str,
    rate_mbps: float,
    burst_kb: int,
    *,
    handle: str = "1:",
    class_id: str = "1:10",
    leaf_handle: str = "10:",
) -> list[Command]:
    return [
        (
            "tc",
            "qdisc",
            "replace",
            "dev",
            interface,
            "root",
            "handle",
            handle,
            "htb",
            "default",
            "10",
        ),
        (
            "tc",
            "class",
            "replace",
            "dev",
            interface,
            "parent",
            "1:",
            "classid",
            class_id,
            "htb",
            "rate",
            _rate(rate_mbps),
            "ceil",
            _rate(rate_mbps),
            "burst",
            _burst(burst_kb),
            "cburst",
            _burst(burst_kb),
        ),
        (
            "tc",
            "qdisc",
            "replace",
            "dev",
            interface,
            "parent",
            "1:10",
            "handle",
            leaf_handle,
            "fq_codel",
            "limit",
            "10240",
            "flows",
            "1024",
            "target",
            "5ms",
            "interval",
            "100ms",
            "quantum",
            "1514",
        ),
    ]


def build_download_commands(
    link: LabLink,
    allocation: ClientAllocation,
    mode: EnforcementMode,
) -> CommandSet:
    """Build the egress shaping commands on the gateway-side veth."""

    if allocation.download_mbps is None:
        raise EnforcementValidationError("download allocation is required")
    rate = allocation.download_mbps
    burst = allocation.burst_for(Direction.DOWNLOAD)
    if mode == EnforcementMode.CAKE:
        commands = _cake_commands(link.download_interface, rate)
    elif mode == EnforcementMode.HTB_FQ_CODEL:
        commands = _htb_commands(link.download_interface, rate, burst)
    else:
        raise EnforcementValidationError("no supported download enforcement mode")
    return CommandSet(
        mode=mode,
        direction=Direction.DOWNLOAD,
        commands=tuple(commands),
        interface=link.download_interface,
    )


def build_upload_commands(
    link: LabLink,
    allocation: ClientAllocation,
    mode: EnforcementMode,
) -> CommandSet:
    """Build ingress redirect + shaping commands for client upload.

    Ingress shaping is only valid on a lab-owned veth. Traffic is redirected to
    a project-owned IFB device with ``matchall`` so IPv4 and IPv6 are covered by
    one explicit rule.
    """

    if allocation.upload_mbps is None:
        raise EnforcementValidationError("upload allocation is required")
    rate = allocation.upload_mbps
    burst = allocation.burst_for(Direction.UPLOAD)
    if mode == EnforcementMode.CAKE:
        shaping = _cake_commands(link.ifb_interface, rate)
    elif mode == EnforcementMode.HTB_FQ_CODEL:
        shaping = _htb_commands(link.ifb_interface, rate, burst)
    else:
        raise EnforcementValidationError("no supported upload enforcement mode")

    redirect = (
        "tc",
        "filter",
        "replace",
        "dev",
        link.upload_interface,
        "parent",
        "ffff:",
        "protocol",
        "all",
        "prio",
        "1",
        "matchall",
        "action",
        "mirred",
        "egress",
        "redirect",
        "dev",
        link.ifb_interface,
    )
    return CommandSet(
        mode=mode,
        direction=Direction.UPLOAD,
        commands=(
            (
                "tc",
                "qdisc",
                "replace",
                "dev",
                link.upload_interface,
                "handle",
                "ffff:",
                "ingress",
            ),
            redirect,
            *shaping,
        ),
        interface=link.upload_interface,
        ifb_interface=link.ifb_interface,
    )


def build_upload_cleanup(link: LabLink) -> tuple[Command, ...]:
    """Remove ingress redirect and the IFB root qdisc for one client."""

    return (
        (
            "tc",
            "qdisc",
            "del",
            "dev",
            link.upload_interface,
            "handle",
            "ffff:",
            "ingress",
        ),
        (
            "tc",
            "qdisc",
            "del",
            "dev",
            link.ifb_interface,
            "root",
        ),
    )


def build_download_cleanup(link: LabLink) -> tuple[Command, ...]:
    return (("tc", "qdisc", "del", "dev", link.download_interface, "root"),)


def ensure_ifb_command(link: LabLink) -> Command:
    """Create a project-owned IFB device.

    This command is only executed after the enforcement layer has verified that
    the IFB name does not already belong to another owner.
    """

    return (
        "ip",
        "link",
        "add",
        link.ifb_interface,
        "type",
        "ifb",
    )


def set_ifb_up_command(link: LabLink) -> Command:
    return ("ip", "link", "set", "dev", link.ifb_interface, "up")


def set_ifb_alias_command(link: LabLink, marker: str) -> Command:
    return (
        "ip",
        "link",
        "set",
        "dev",
        link.ifb_interface,
        "alias",
        marker,
    )


def delete_ifb_command(link: LabLink) -> Command:
    return ("ip", "link", "del", "dev", link.ifb_interface)

"""Bounded, project-owned rollback for Linux traffic control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from qos.models import (
    LabLink,
    RollbackError,
)
from qos.runner import CommandRunner, require_success
from qos.verifier import read_interface_state


@dataclass(frozen=True)
class InterfaceSnapshot:
    interface: str
    root_kind: str | None
    root_rate_mbps: float | None
    ingress_present: bool

    @property
    def restorable(self) -> bool:
        return self.root_kind in (None, "noqueue") and not self.ingress_present


def capture_snapshots(
    runner: CommandRunner,
    interfaces: Iterable[str],
) -> dict[str, InterfaceSnapshot]:
    snapshots: dict[str, InterfaceSnapshot] = {}
    for interface in sorted(set(interfaces)):
        state = read_interface_state(
            runner,
            interface,
            include_classes=True,
            include_filters=True,
        )
        snapshots[interface] = InterfaceSnapshot(
            interface=interface,
            root_kind=state.root_kind,
            root_rate_mbps=state.root_rate_mbps,
            ingress_present=state.ingress_present,
        )
    return snapshots


def _delete_qdiscs(runner: CommandRunner, interface: str, *, ingress: bool = True) -> None:
    state = read_interface_state(
        runner,
        interface,
        include_classes=False,
        include_filters=False,
    )
    if state.root_kind not in (None, "noqueue"):
        require_success(
            runner.run(("tc", "qdisc", "del", "dev", interface, "root"))
        )
    if ingress and state.ingress_present:
        require_success(
            runner.run(
                ("tc", "qdisc", "del", "dev", interface, "handle", "ffff:", "ingress")
            )
        )


def _restore_one(runner: CommandRunner, snapshot: InterfaceSnapshot) -> None:
    if not snapshot.restorable:
        raise RollbackError("previous qdisc state is not restorable")
    _delete_qdiscs(runner, snapshot.interface)
    kind = snapshot.root_kind
    if kind == "fq_codel":
        require_success(
            runner.run(
                ("tc", "qdisc", "replace", "dev", snapshot.interface, "root", "fq_codel")
            )
        )
    elif kind == "cake":
        require_success(
            runner.run(
                (
                    "tc",
                    "qdisc",
                    "replace",
                    "dev",
                    snapshot.interface,
                    "root",
                    "cake",
                    "bandwidth",
                    f"{snapshot.root_rate_mbps:g}mbit",
                    "besteffort",
                )
            )
        )
    elif kind == "htb":
        rate = snapshot.root_rate_mbps
        burst = max(32, min(64_000, int(rate * 2 + 64)))
        require_success(
            runner.run(
                (
                    "tc",
                    "qdisc",
                    "replace",
                    "dev",
                    snapshot.interface,
                    "root",
                    "handle",
                    "1:",
                    "htb",
                    "default",
                    "10",
                )
            )
        )
        require_success(
            runner.run(
                (
                    "tc",
                    "class",
                    "replace",
                    "dev",
                    snapshot.interface,
                    "parent",
                    "1:",
                    "classid",
                    "1:10",
                    "htb",
                    "rate",
                    f"{rate:g}mbit",
                    "ceil",
                    f"{rate:g}mbit",
                    "burst",
                    f"{burst}kb",
                    "cburst",
                    f"{burst}kb",
                )
            )
        )
        require_success(
            runner.run(
                (
                    "tc",
                    "qdisc",
                    "replace",
                    "dev",
                    snapshot.interface,
                    "parent",
                    "1:10",
                    "handle",
                    "10:",
                    "fq_codel",
                )
            )
        )
    elif kind == "tbf":
        rate = snapshot.root_rate_mbps
        burst = max(32, min(64_000, int(rate * 2 + 100)))
        require_success(
            runner.run(
                (
                    "tc",
                    "qdisc",
                    "replace",
                    "dev",
                    snapshot.interface,
                    "root",
                    "tbf",
                    "rate",
                    f"{rate:g}mbit",
                    "burst",
                    f"{burst}kb",
                    "latency",
                    "50ms",
                )
            )
        )
    # None/noqueue: leaving the root qdisc deleted restores the kernel default.


def restore_snapshots(
    runner: CommandRunner,
    snapshots: Iterable[InterfaceSnapshot],
    *,
    owned_interfaces: Iterable[str],
) -> tuple[bool, tuple[str, ...]]:
    """Restore only project-owned interfaces; report every failure."""

    owned = set(owned_interfaces)
    failures: list[str] = []
    for snapshot in snapshots:
        if snapshot.interface not in owned:
            failures.append("refused_to_restore_unowned_interface")
            continue
        try:
            _restore_one(runner, snapshot)
            actual = read_interface_state(
                runner,
                snapshot.interface,
                include_classes=False,
                include_filters=False,
            )
            if (
                actual.root_kind != snapshot.root_kind
                or actual.ingress_present != snapshot.ingress_present
            ):
                raise RollbackError("restored qdisc state did not verify")
        except Exception:
            failures.append("restore_failed")
    return not failures, tuple(dict.fromkeys(failures))


def remove_project_qdiscs(
    runner: CommandRunner,
    links: Iterable[LabLink],
    *,
    owned_interfaces: Iterable[str],
    delete_ifb: bool = True,
) -> tuple[bool, tuple[str, ...]]:
    """Remove only project-owned root/ingress qdiscs and IFB devices."""

    owned = set(owned_interfaces)
    failures: list[str] = []
    for link in links:
        for interface in (link.download_interface, link.upload_interface):
            if interface not in owned:
                failures.append("refused_to_remove_unowned_interface")
                continue
            try:
                state = read_interface_state(
                    runner,
                    interface,
                    include_classes=False,
                    include_filters=False,
                )
                if state.root_kind not in (None, "noqueue"):
                    require_success(
                        runner.run(("tc", "qdisc", "del", "dev", interface, "root"))
                    )
                if state.ingress_present:
                    require_success(
                        runner.run(
                            (
                                "tc",
                                "qdisc",
                                "del",
                                "dev",
                                interface,
                                "handle",
                                "ffff:",
                                "ingress",
                            )
                        )
                    )
            except Exception:
                failures.append("qdisc_removal_failed")
        if link.ifb_interface in owned:
            try:
                state = read_interface_state(
                    runner,
                    link.ifb_interface,
                    include_classes=False,
                    include_filters=False,
                )
                if state.root_kind not in (None, "noqueue"):
                    require_success(
                        runner.run(
                            ("tc", "qdisc", "del", "dev", link.ifb_interface, "root")
                        )
                    )
                if delete_ifb:
                    require_success(
                        runner.run(("ip", "link", "del", "dev", link.ifb_interface))
                    )
            except Exception:
                failures.append("ifb_removal_failed")
    return not failures, tuple(dict.fromkeys(failures))

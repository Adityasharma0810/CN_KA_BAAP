"""Kernel readback parsing and verification for Linux shaping."""

from __future__ import annotations

import re
from typing import Iterable

from qos.models import (
    ClientAllocation,
    Direction,
    EnforcementMode,
    LabLink,
    QdiscReadback,
    VerificationError,
    VerificationResult,
)
from qos.runner import CommandRunner


_ROOT_QDISC = re.compile(r"^qdisc\s+(\S+)\s+(\S+)\s+root\b(.*)$")
_CAKE_BANDWIDTH = re.compile(r"\bbandwidth\s+([0-9]+(?:\.[0-9]+)?)([KMG]?)bit", re.IGNORECASE)
_HTB_CLASS_RATE = re.compile(r"\brate\s+([0-9]+(?:\.[0-9]+)?)([KMG]?)bit", re.IGNORECASE)
_FQ_CODEL_LEAF = re.compile(r"^qdisc\s+fq_codel\s+\S+\s+parent\s+(\S+)")
_INGRESS = re.compile(r"^qdisc\s+ingress\s+ffff:")
_REDIRECT = re.compile(
    r"(?:redirect\s+dev\s+(\S+)|Redirect\s+to\s+device\s+([A-Za-z0-9_.-]+))",
    re.IGNORECASE,
)
_MULTIPLIERS = {"": 1.0, "K": 1e-3, "M": 1.0, "G": 1e3}


def parse_rate_mbps(value: str, unit: str) -> float:
    multiplier = _MULTIPLIERS.get(unit.upper(), 1.0)
    return round(float(value) * multiplier, 6)


def parse_root_qdisc(output: str) -> tuple[str | None, float | None]:
    for line in output.splitlines():
        match = _ROOT_QDISC.match(line.strip())
        if match is None:
            continue
        kind = match.group(1).lower()
        rest = match.group(3)
        rate = None
        cake_match = _CAKE_BANDWIDTH.search(rest)
        if cake_match is not None:
            rate = parse_rate_mbps(cake_match.group(1), cake_match.group(2))
        return kind, rate
    return None, None


def parse_htb_class_rate(output: str) -> float | None:
    for line in output.splitlines():
        if not line.strip().startswith("class htb"):
            continue
        match = _HTB_CLASS_RATE.search(line)
        if match is not None:
            return parse_rate_mbps(match.group(1), match.group(2))
    return None


def parse_fq_codel_parents(output: str) -> tuple[str, ...]:
    parents = []
    for line in output.splitlines():
        match = _FQ_CODEL_LEAF.match(line.strip())
        if match is not None:
            parents.append(match.group(1))
    return tuple(parents)


def parse_ingress_present(output: str) -> bool:
    return any(_INGRESS.match(line.strip()) for line in output.splitlines())


def parse_redirect_targets(output: str) -> tuple[str, ...]:
    targets = []
    for line in output.splitlines():
        for match in _REDIRECT.finditer(line):
            target = match.group(1) or match.group(2)
            if target:
                targets.append(target)
    return tuple(dict.fromkeys(targets))


def _run(runner: CommandRunner, args: tuple[str, ...]) -> str:
    result = runner.run(args)
    if result.returncode != 0:
        raise VerificationError("kernel traffic-control state could not be read")
    return result.stdout


def read_interface_state(
    runner: CommandRunner,
    interface: str,
    *,
    include_classes: bool = True,
    include_filters: bool = False,
) -> QdiscReadback:
    qdisc_output = _run(runner, ("tc", "qdisc", "show", "dev", interface))
    root_kind, root_rate = parse_root_qdisc(qdisc_output)
    # ``tc qdisc show`` lists child qdiscs (including a classful root's leaf)
    # while ``tc class show`` reports the HTB class rate. Parse each from the
    # command that actually emits it.
    leaf_parents: tuple[str, ...] = parse_fq_codel_parents(qdisc_output)
    if include_classes:
        class_output = _run(runner, ("tc", "class", "show", "dev", interface))
        if root_rate is None:
            root_rate = parse_htb_class_rate(class_output)
    targets: tuple[str, ...] = ()
    if include_filters:
        filter_output = _run(
            runner,
            ("tc", "filter", "show", "dev", interface, "parent", "ffff:"),
        )
        targets = parse_redirect_targets(filter_output)
    return QdiscReadback(
        interface=interface,
        root_kind=root_kind,
        root_rate_mbps=root_rate,
        leaf_kinds=tuple(
            "fq_codel" for _ in leaf_parents
        ),
        ingress_present=parse_ingress_present(qdisc_output),
        redirect_targets=targets,
    )


def _rate_matches(expected: float, actual: float | None) -> bool:
    if actual is None:
        return False
    tolerance = max(0.5, expected * 0.02)
    return abs(actual - expected) <= tolerance


def verify_direction(
    *,
    link: LabLink,
    allocation: ClientAllocation,
    mode: EnforcementMode,
    direction: Direction,
    runner: CommandRunner,
) -> VerificationResult:
    errors: list[str] = []
    readbacks: list[QdiscReadback] = []
    expected_rate = allocation.rate_for(direction)
    if expected_rate is None:
        return VerificationResult(True, mode, (), ())

    expected_kind = (
        "cake" if mode == EnforcementMode.CAKE else "htb"
    )
    if direction == Direction.DOWNLOAD:
        state = read_interface_state(runner, link.download_interface, include_classes=True)
        readbacks.append(state)
        if state.root_kind != expected_kind:
            errors.append("download_root_qdisc_mismatch")
        if not _rate_matches(expected_rate, state.root_rate_mbps):
            errors.append("download_rate_mismatch")
        if mode == EnforcementMode.HTB_FQ_CODEL and "fq_codel" not in state.leaf_kinds:
            errors.append("download_fq_codel_missing")
    else:
        ingress = read_interface_state(
            runner,
            link.upload_interface,
            include_classes=False,
            include_filters=True,
        )
        readbacks.append(ingress)
        if not ingress.ingress_present:
            errors.append("upload_ingress_qdisc_missing")
        if link.ifb_interface not in ingress.redirect_targets:
            errors.append("upload_redirect_missing")
        ifb_state = read_interface_state(
            runner,
            link.ifb_interface,
            include_classes=True,
        )
        readbacks.append(ifb_state)
        if ifb_state.root_kind != expected_kind:
            errors.append("upload_root_qdisc_mismatch")
        if not _rate_matches(expected_rate, ifb_state.root_rate_mbps):
            errors.append("upload_rate_mismatch")
        if mode == EnforcementMode.HTB_FQ_CODEL and "fq_codel" not in ifb_state.leaf_kinds:
            errors.append("upload_fq_codel_missing")

    return VerificationResult(
        ok=not errors,
        mode=mode,
        errors=tuple(errors),
        readback=tuple(readbacks),
    )


def verify_plan(
    *,
    links: Iterable[LabLink],
    allocations: Iterable[ClientAllocation],
    mode: EnforcementMode,
    runner: CommandRunner,
) -> VerificationResult:
    by_client = {link.client_id: link for link in links}
    errors: list[str] = []
    readbacks: list[QdiscReadback] = []
    for allocation in allocations:
        link = by_client.get(allocation.client_id)
        if link is None:
            errors.append("missing_lab_link")
            continue
        for direction in (Direction.DOWNLOAD, Direction.UPLOAD):
            result = verify_direction(
                link=link,
                allocation=allocation,
                mode=mode,
                direction=direction,
                runner=runner,
            )
            errors.extend(result.errors)
            readbacks.extend(result.readback)
    return VerificationResult(
        ok=not errors,
        mode=mode,
        errors=tuple(dict.fromkeys(errors)),
        readback=tuple(readbacks),
    )

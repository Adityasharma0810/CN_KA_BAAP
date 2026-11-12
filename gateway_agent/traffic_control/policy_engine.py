"""Max-min QoE policy engine (F5) for the gateway agent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeviceDemand:
    client_id: str
    measured_qoe: float | None
    min_floor_mbps: float
    min_rate_mbps: float
    max_rate_mbps: float
    weight: float = 1.0


@dataclass
class AllocationResult:
    allocations: dict[str, float]
    worst_qoe: float | None
    feasible: bool
    infeasible_reason: str | None
    total_allocated_mbps: float
    note: str | None = None


def optimize(capacity_mbps: float, devices: list[DeviceDemand]) -> AllocationResult:
    """Constrained max-min QoE allocation.

    Maximizes the worst device's normalized QoE subject to physical capacity
    and per-device min/max rate bounds.
    """
    capacity = max(float(capacity_mbps), 0.0)
    n = len(devices)
    if n == 0:
        return AllocationResult({}, None, True, None, 0.0, "no_devices")

    floors = [max(d.min_floor_mbps, 0.0) for d in devices]
    floor_sum = sum(floors)
    infeasible_reason = None
    note = None
    if floor_sum > capacity + 1e-9:
        scale = capacity / floor_sum if floor_sum > 0 else 0.0
        floors = [f * scale for f in floors]
        infeasible_reason = "minimum_service_floors_exceed_capacity"
        note = (
            f"Requested floors sum to {floor_sum:.2f} Mbps > {capacity:.2f} Mbps "
            "available; floors scaled proportionally."
        )

    allocation = list(floors)
    remaining = capacity - sum(allocation)
    active = [i for i in range(n) if allocation[i] < devices[i].max_rate_mbps + 1e-12]
    while remaining > 1e-9 and active:
        total_w = sum(devices[i].weight for i in active)
        if total_w <= 0:
            break
        step = remaining / total_w
        new_active = []
        for i in active:
            headroom = devices[i].max_rate_mbps - allocation[i]
            add = min(step * devices[i].weight, headroom)
            allocation[i] += add
            remaining -= add
            if allocation[i] < devices[i].max_rate_mbps - 1e-9:
                new_active.append(i)
        active = new_active

    allocations = {devices[i].client_id: round(max(allocation[i], 0.0), 4) for i in range(n)}
    total_allocated = sum(allocations.values())
    worst_qoe = min((d.measured_qoe for d in devices if d.measured_qoe is not None), default=None)
    return AllocationResult(
        allocations=allocations,
        worst_qoe=worst_qoe,
        feasible=infeasible_reason is None,
        infeasible_reason=infeasible_reason,
        total_allocated_mbps=round(total_allocated, 4),
        note=note,
    )

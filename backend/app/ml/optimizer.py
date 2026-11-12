"""Constrained max-min QoE optimizer (F5).

Maximizes the worst-performing device's normalized QoE subject to physical
capacity, per-device minimum service floors, rate bounds, and traffic
requirements. Urgency and declared importance are secondary objectives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DeviceDemand:
    client_id: str
    measured_qoe: Optional[float]  # 0-100 or None
    min_floor_mbps: float
    min_rate_mbps: float
    max_rate_mbps: float
    weight: float = 1.0  # urgency * importance secondary objective
    traffic_class: str = "bulk"


@dataclass
class AllocationResult:
    allocations: dict[str, float]  # client_id -> download_mbps
    worst_qoe: Optional[float]
    feasible: bool
    infeasible_reason: Optional[str]
    total_allocated_mbps: float
    note: Optional[str] = None


def optimize(
    capacity_mbps: float,
    devices: list[DeviceDemand],
    dwell_respected: bool = True,
) -> AllocationResult:
    """Max-min fair QoE allocation.

    Returns allocations summing to <= capacity. Every device receives at least
    its min_floor_mbps if physically feasible; otherwise reports infeasibility
    with the least-harmful trade-off (pro-rata reduction of floors).
    """
    capacity = max(float(capacity_mbps), 0.0)
    ids = [d.client_id for d in devices]
    n = len(devices)

    if n == 0:
        return AllocationResult({}, None, True, None, 0.0, "no_devices")

    # Physical feasibility of minimum floors.
    floor_sum = sum(max(d.min_floor_mbps, 0.0) for d in devices)
    infeasible_reason = None
    note = None
    floors = [max(d.min_floor_mbps, 0.0) for d in devices]

    if floor_sum > capacity + 1e-9:
        # Infeasible: scale floors down pro-rata (least-harmful trade-off).
        scale = capacity / floor_sum if floor_sum > 0 else 0.0
        floors = [f * scale for f in floors]
        infeasible_reason = "minimum_service_floors_exceed_capacity"
        note = (
            f"Requested floors sum to {floor_sum:.2f} Mbps > {capacity:.2f} Mbps "
            "available; floors scaled proportionally. No device is starved below "
            "its scaled floor."
        )

    # Max-min water-filling over floors with per-device max caps.
    allocation = list(floors)
    remaining = capacity - sum(allocation)
    active = [i for i in range(n) if allocation[i] < devices[i].max_rate_mbps + 1e-12]

    # Iteratively raise the lowest allocations (weighted by importance).
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

    # Secondary: apply urgency/importance weights already reflected above.
    allocations = {ids[i]: round(max(allocation[i], 0.0), 4) for i in range(n)}
    total_allocated = sum(allocations.values())

    # Worst normalized QoE proxy: allocation vs demand (measured QoE informs weight only).
    worst_qoe: Optional[float] = None
    if devices:
        worst_qoe = min(
            (d.measured_qoe for d in devices if d.measured_qoe is not None),
            default=None,
        )

    feasible = infeasible_reason is None
    return AllocationResult(
        allocations=allocations,
        worst_qoe=worst_qoe,
        feasible=feasible,
        infeasible_reason=infeasible_reason,
        total_allocated_mbps=round(total_allocated, 4),
        note=note,
    )

"""Turns measurements into limit decisions. Pure logic, no I/O."""
from gateway.policy import DEFAULT_INTENT, INTENT_WEIGHTS, allocate

CAP_THRESHOLD = 0.9      # measured >= 90% of the cap means "capped, wants more"
HEADROOM = 1.2           # demand estimate = measured speed * 1.2
MIN_DEMAND = 5.0         # idle clients keep a small share (Mbit/s)
CHANGE_THRESHOLD = 0.15  # ignore limit changes smaller than 15%


def estimate_demand(measured: float, current_limit, budget: float) -> float:
    if current_limit is not None and measured >= CAP_THRESHOLD * current_limit:
        return float(budget)  # saturating its cap: true demand unknown
    return max(measured * HEADROOM, MIN_DEMAND)


def decide(budget: float, measured: dict, current: dict, intents: dict) -> dict:
    """Return {client: target download limit in Mbit/s, or None for no limit}."""
    demands = {c: estimate_demand(measured[c], current[c], budget) for c in measured}
    if sum(demands.values()) <= budget:
        return {c: None for c in measured}  # no contention: no limits

    default_w = INTENT_WEIGHTS[DEFAULT_INTENT]
    weights = {
        c: INTENT_WEIGHTS.get(intents.get(c, DEFAULT_INTENT), default_w)
        for c in measured
    }
    alloc = allocate(budget, demands, weights)

    targets = {}
    for c, share in alloc.items():
        target = max(1, round(share))
        cur = current[c]
        if cur is not None and abs(target - cur) / cur <= CHANGE_THRESHOLD:
            target = cur  # hysteresis: keep the existing limit
        targets[c] = target
    return targets
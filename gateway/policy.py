"""Experience Budget policy: split a shared bandwidth budget by intent."""

# Higher weight = bigger share when the link is contended. Tunable.
INTENT_WEIGHTS = {
    "call": 8.0,
    "gaming": 6.0,
    "streaming": 4.0,
    "browsing": 2.0,
    "download": 1.0,
}
DEFAULT_INTENT = "browsing"


def allocate(budget: float, demands: dict, weights: dict) -> dict:
    """Weighted max-min fair split of `budget` (Mbit/s).

    demands: {client: Mbit/s the client wants}
    weights: {client: priority weight, must be > 0}
    Returns {client: Mbit/s allocated}. A client never gets more than it
    demands, and the total never exceeds the budget.
    """
    alloc = {}
    remaining = dict(demands)
    budget_left = float(budget)

    while remaining:
        total_w = sum(weights[c] for c in remaining)
        share = {c: budget_left * weights[c] / total_w for c in remaining}
        satisfied = [c for c in remaining if remaining[c] <= share[c]]
        if not satisfied:
            # Everyone left wants more than their fair share: split by weight.
            alloc.update(share)
            break
        for c in satisfied:
            alloc[c] = remaining[c]
            budget_left -= remaining[c]
            del remaining[c]

    return alloc
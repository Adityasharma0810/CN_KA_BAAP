"""Minimal example for the Experience Budget QoE warner."""
import json
from eb_runtime import ExperienceBudgetModels


def main():
    eb = ExperienceBudgetModels.load(".")
    warner = eb.qoe_warner(horizon_s=10)  # supported: 5 or 10 seconds

    # Replace these demonstration values with live measurements.
    record = {
        # Network-wide snapshot
        "qdelay_ms": 8.0,
        "rho": 0.82,
        "cap": 100.0,
        "mode_fq": 0,
        "n_call_net": 1,
        "n_game_net": 0,
        "n_stream_net": 1,
        "n_bulk_net": 1,
        # This device's measurements
        "delay": 35.0,
        "jitter": 4.0,
        "loss": 0.001,  # fraction: 0.001 = 0.1%
        "thr": 8.0,
        "n_flows": 1,
        "has_call": 1,
        "has_game": 0,
        "has_stream": 0,
        "has_bulk": 0,
        "qoe": 0.92,   # must be supplied by your QoE scoring layer, 0..1
        "buf_min": 18.0,
    }

    result = None
    for t_sec in range(20):  # one record per second; 16 samples fill the longest lag
        result = warner.push("device-1", t_sec, record)

    print(json.dumps(result, indent=2, allow_nan=True))


if __name__ == "__main__":
    main()

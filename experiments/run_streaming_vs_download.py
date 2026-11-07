#!/usr/bin/env python3
"""Second experiment: where intent weighting actually matters.

client1 = a "streaming" client that wants STREAM_RATE Mbit/s (one TCP stream,
paced), client2 = a greedy download (4 parallel TCP streams). Both want more
than an equal share of the 100 Mbit/s plan.

Three modes, interleaved across repeats:
  nopolicy  only the shared bottleneck (plain FIFO, TCP shares per flow)
  equal     the policy loop with equal weights for both clients
  intent    the policy loop with streaming (weight 4) vs download (weight 1)

Reuses helpers from run_call_vs_download.py (same folder).

Run from the repo root as your normal user, with the gateway API and the
iperf3 servers (ports 5201 and 5202) already running:

    sudo -v && python3 experiments/run_streaming_vs_download.py --runs 5
"""
import argparse
import csv
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from run_call_vs_download import (BUDGET, UNIT, api, parse_download, parse_ping,
                                  port_open)

MODES = ["nopolicy", "equal", "intent"]
INTENTS = {"equal": ("browsing", "browsing"), "intent": ("streaming", "download")}
TCP_RE = re.compile(
    r"\[\s*\d+\]\s+\S+\s+sec\s+[\d.]+ \S+\s+([\d.]+) ([KMG])bits/sec\s+receiver"
)


def parse_stream(text):
    m = TCP_RE.search(text)
    if not m:
        raise RuntimeError("could not parse the streaming client's receiver line")
    return float(m.group(1)) * UNIT[m.group(2)]


def set_mode(mode):
    api("POST", "/policy", {"enabled": False, "budget_mbps": BUDGET})  # clears limits
    time.sleep(1)
    if mode == "nopolicy":
        return
    i1, i2 = INTENTS[mode]
    api("POST", "/clients/1/intent", {"intent": i1})
    api("POST", "/clients/2/intent", {"intent": i2})
    api("POST", "/policy", {"enabled": True, "budget_mbps": BUDGET})


def run_once(duration, omit, streams, rate):
    n_ping = int((omit + duration) * 5) - 5
    ns = ["sudo", "ip", "netns", "exec"]
    cmds = {
        "stream": ns + ["client1", "iperf3", "-c", "10.50.0.1", "-p", "5202", "-R",
                        "-b", f"{rate}M", "-O", str(omit), "-t", str(duration)],
        "download": ns + ["client2", "iperf3", "-c", "10.50.0.1", "-p", "5201", "-R",
                          "-P", str(streams), "-O", str(omit), "-t", str(duration)],
        "ping": ns + ["client1", "ping", "-i", "0.2", "-c", str(n_ping), "10.50.0.1"],
    }
    procs = {
        k: subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for k, c in cmds.items()
    }
    out = {k: p.communicate()[0] for k, p in procs.items()}

    stream = parse_stream(out["stream"])
    dl = parse_download(out["download"])
    row = {
        "stream_mbps": stream,
        "stream_shortfall_pct": max(0.0, 1 - stream / rate) * 100,
        "dl_mbps": dl,
        "total_mbps": stream + dl,
        "stream_rtt_avg_ms": parse_ping(out["ping"], skip=int(omit * 5))["rtt_avg_ms"],
    }
    return row, out


def summarize(rows):
    metrics = ["stream_mbps", "stream_shortfall_pct", "dl_mbps", "total_mbps",
               "stream_rtt_avg_ms"]
    print(f"\n{'metric':<22}" + "".join(f"{m:>22}" for m in MODES))
    for metric in metrics:
        cells = []
        for mode in MODES:
            vals = [r[metric] for r in rows if r["mode"] == mode]
            if not vals:
                cells.append("n/a")
                continue
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            cells.append(f"{statistics.mean(vals):.1f} +/- {sd:.1f}")
        print(f"{metric:<22}" + "".join(f"{c:>22}" for c in cells))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5, help="repeats per mode")
    ap.add_argument("--duration", type=int, default=20, help="measured seconds")
    ap.add_argument("--omit", type=int, default=8, help="warm-up seconds, not measured")
    ap.add_argument("--streams", type=int, default=4, help="parallel download streams")
    ap.add_argument("--stream-rate", type=int, default=60,
                    help="Mbit/s the streaming client asks for")
    args = ap.parse_args()

    try:
        api("GET", "/health")
    except Exception as e:
        sys.exit(f"Gateway API not reachable: {e}")
    for port in (5201, 5202):
        if not port_open(port):
            sys.exit(f"No iperf3 server on port {port}. Start: iperf3 -s -p {port} -D")
    if subprocess.run(["sudo", "-v"]).returncode != 0:
        sys.exit("sudo failed")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = Path("experiments/reports")
    outdir.mkdir(parents=True, exist_ok=True)
    rawdir = Path("/tmp") / f"eb_stream_runs_{stamp}"
    rawdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / f"streaming_vs_download_{stamp}.csv"

    subprocess.run(["sudo", "bash", "scripts/set_bottleneck.sh", str(BUDGET)], check=True)

    rows = []
    try:
        for i in range(1, args.runs + 1):
            order = MODES[(i - 1) % len(MODES):] + MODES[:(i - 1) % len(MODES)]  # rotate
            for mode in order:
                print(f"run {i}/{args.runs}  mode={mode} ...", flush=True)
                set_mode(mode)
                try:
                    row, raw = run_once(args.duration, args.omit, args.streams,
                                        args.stream_rate)
                except RuntimeError as e:
                    print(f"  skipped: {e}")
                    continue
                for k, text in raw.items():
                    (rawdir / f"run{i}_{mode}_{k}.txt").write_text(text)
                if row["stream_mbps"] > args.stream_rate * 1.15:
                    print("  WARNING: streaming client exceeded its target rate, so "
                          "iperf3 may be ignoring -b for TCP in reverse mode.")
                row.update({"run": i, "mode": mode})
                rows.append(row)
                print(f"  stream={row['stream_mbps']:.1f}  download={row['dl_mbps']:.1f}  "
                      f"total={row['total_mbps']:.1f} Mbit/s")
                set_mode("nopolicy")
                time.sleep(5)
    finally:
        try:
            api("POST", "/policy", {"enabled": False, "budget_mbps": BUDGET})
        except Exception:
            pass
        subprocess.run(["sudo", "bash", "scripts/set_bottleneck.sh", "off"])

    if not rows:
        sys.exit("No successful runs.")
    fields = ["run", "mode", "stream_mbps", "stream_shortfall_pct", "dl_mbps",
              "total_mbps", "stream_rtt_avg_ms"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(r[k], 3) if isinstance(r[k], float) else r[k]) for k in fields})
    summarize(rows)
    print(f"\nCSV: {csv_path}\nRaw outputs: {rawdir}")


if __name__ == "__main__":
    main()
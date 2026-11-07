#!/usr/bin/env python3
"""Repeated experiment: a 5 Mbit/s "call" (client1) competing with a greedy
multi-stream download (client2) through a shared bottleneck.

Compares: no policy vs the intent policy. Interleaves the modes so slow drift
in the VM affects both equally, and writes one CSV row per run.

Run from the repo root as your normal user, with the gateway API and the
iperf3 servers (ports 5201 and 5202) already running:

    sudo -v && python3 experiments/run_call_vs_download.py --runs 5
"""
import argparse
import csv
import json
import re
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

API = "http://localhost:8000"
BUDGET = 100  # simulated plan, Mbit/s (also the shared bottleneck rate)
MODES = ["nopolicy", "policy"]
UNIT = {"K": 1e-3, "M": 1.0, "G": 1e3}

UDP_RE = re.compile(
    r"([\d.]+) ([KMG])bits/sec\s+([\d.]+) ms\s+(\d+)/(\d+) \(([\d.eE+-]+)%\)\s+receiver"
)
SUM_RE = re.compile(
    r"\[SUM\]\s+\S+\s+sec\s+[\d.]+ \S+\s+([\d.]+) ([KMG])bits/sec\s+receiver"
)
PING_RE = re.compile(r"time=([\d.]+) ms")


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def port_open(port):
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex(("10.50.0.1", port)) == 0


def parse_call(text):
    m = UDP_RE.search(text)
    if not m:
        raise RuntimeError("could not parse the call (UDP) receiver line")
    return {
        "call_mbps": float(m.group(1)) * UNIT[m.group(2)],
        "call_jitter_ms": float(m.group(3)),
        "call_loss_pct": float(m.group(6)),
    }


def parse_download(text):
    m = SUM_RE.search(text)
    if not m:
        raise RuntimeError("could not parse the download [SUM] receiver line")
    return float(m.group(1)) * UNIT[m.group(2)]


def parse_ping(text, skip):
    rtts = [float(x) for x in PING_RE.findall(text)][skip:]
    if len(rtts) < 10:
        raise RuntimeError(f"too few ping samples after warm-up ({len(rtts)})")
    rtts_sorted = sorted(rtts)
    return {
        "rtt_avg_ms": statistics.mean(rtts),
        "rtt_p95_ms": rtts_sorted[int(0.95 * (len(rtts_sorted) - 1))],
        "rtt_max_ms": rtts_sorted[-1],
    }


def set_mode(mode):
    api("POST", "/policy", {"enabled": False, "budget_mbps": BUDGET})  # clears limits
    time.sleep(1)
    if mode == "policy":
        api("POST", "/policy", {"enabled": True, "budget_mbps": BUDGET})


def run_once(duration, omit, streams):
    """Start the three flows together, wait, and return parsed metrics."""
    n_ping = int((omit + duration) * 5) - 5
    ns = ["sudo", "ip", "netns", "exec"]
    cmds = {
        "call": ns + ["client1", "iperf3", "-c", "10.50.0.1", "-p", "5202", "-u",
                      "-b", "5M", "-R", "-O", str(omit), "-t", str(duration)],
        "download": ns + ["client2", "iperf3", "-c", "10.50.0.1", "-p", "5201",
                          "-R", "-P", str(streams), "-O", str(omit), "-t", str(duration)],
        "ping": ns + ["client1", "ping", "-i", "0.2", "-c", str(n_ping), "10.50.0.1"],
    }
    procs = {
        k: subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for k, c in cmds.items()
    }
    out = {k: p.communicate()[0] for k, p in procs.items()}

    row = parse_call(out["call"])
    row["dl_mbps"] = parse_download(out["download"])
    row.update(parse_ping(out["ping"], skip=int(omit * 5)))
    return row, out


def summarize(rows):
    metrics = ["call_loss_pct", "call_jitter_ms", "rtt_avg_ms", "rtt_p95_ms",
               "rtt_max_ms", "dl_mbps"]
    print(f"\n{'metric':<16}" + "".join(f"{m:>24}" for m in MODES))
    for metric in metrics:
        cells = []
        for mode in MODES:
            vals = [r[metric] for r in rows if r["mode"] == mode]
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            cells.append(f"{statistics.mean(vals):>10.2f} +/- {sd:<8.2f}")
        print(f"{metric:<16}" + "".join(f"{c:>24}" for c in cells))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5, help="repeats per mode")
    ap.add_argument("--duration", type=int, default=20, help="measured seconds")
    ap.add_argument("--omit", type=int, default=8, help="warm-up seconds, not measured")
    ap.add_argument("--streams", type=int, default=4, help="parallel download streams")
    args = ap.parse_args()

    # Pre-flight checks
    try:
        api("GET", "/health")
    except Exception as e:
        sys.exit(f"Gateway API not reachable on {API}: {e}")
    for port in (5201, 5202):
        if not port_open(port):
            sys.exit(f"No iperf3 server on port {port}. Start: iperf3 -s -p {port} -D")
    if subprocess.run(["sudo", "-v"]).returncode != 0:
        sys.exit("sudo failed")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = Path("experiments/reports")
    outdir.mkdir(parents=True, exist_ok=True)
    rawdir = Path("/tmp") / f"eb_runs_{stamp}"
    rawdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / f"call_vs_download_{stamp}.csv"

    api("POST", "/clients/1/intent", {"intent": "call"})
    api("POST", "/clients/2/intent", {"intent": "download"})
    subprocess.run(["sudo", "bash", "scripts/set_bottleneck.sh", str(BUDGET)], check=True)

    rows = []
    try:
        for i in range(1, args.runs + 1):
            order = MODES if i % 2 else MODES[::-1]  # alternate order each repeat
            for mode in order:
                print(f"run {i}/{args.runs}  mode={mode} ...", flush=True)
                set_mode(mode)
                try:
                    row, raw = run_once(args.duration, args.omit, args.streams)
                except RuntimeError as e:
                    print(f"  skipped: {e}")
                    continue
                for k, text in raw.items():
                    (rawdir / f"run{i}_{mode}_{k}.txt").write_text(text)
                row.update({"run": i, "mode": mode})
                rows.append(row)
                print(f"  loss={row['call_loss_pct']:.2f}%  rtt avg={row['rtt_avg_ms']:.1f} ms  "
                      f"download={row['dl_mbps']:.1f} Mbit/s")
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
    fields = ["run", "mode", "call_loss_pct", "call_jitter_ms", "call_mbps",
              "rtt_avg_ms", "rtt_p95_ms", "rtt_max_ms", "dl_mbps"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(r[k], 3) if isinstance(r[k], float) else r[k]) for k in fields})
    summarize(rows)
    print(f"\nCSV: {csv_path}\nRaw outputs: {rawdir}")


if __name__ == "__main__":
    main()
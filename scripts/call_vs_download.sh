#!/usr/bin/env bash
# One run: client1 = 5 Mbit/s UDP "call" plus a ping probe, client2 = greedy
# TCP download (STREAMS parallel streams), all through the shared bottleneck.
# Run as your normal user.
# Usage: bash scripts/call_vs_download.sh <label> [duration_seconds]
#        STREAMS=1 bash scripts/call_vs_download.sh <label>   (single stream)
set -uo pipefail

LABEL="${1:?usage: $0 <label> [duration_seconds]}"
DUR="${2:-20}"
STREAMS="${STREAMS:-4}"
OUT="/tmp/eb_${LABEL}"
mkdir -p "$OUT"

sudo -v

sudo ip netns exec client1 iperf3 -c 10.50.0.1 -p 5202 -u -b 5M -R -t "$DUR" > "$OUT/call.txt" 2>&1 &
P1=$!
sudo ip netns exec client2 iperf3 -c 10.50.0.1 -p 5201 -R -P "$STREAMS" -t "$DUR" > "$OUT/download.txt" 2>&1 &
P2=$!
sudo ip netns exec client1 ping -i 0.2 -c $((DUR * 5 - 5)) 10.50.0.1 > "$OUT/ping.txt" 2>&1 &
P3=$!

# Snapshot halfway through, while any limits are still in place.
sleep $((DUR / 2))
curl -sS --max-time 3 localhost:8000/policy > "$OUT/policy_mid.txt" 2>&1
for d in br-lab veth-c1-br veth-c2-br; do
  echo "== $d"
  tc -s qdisc show dev "$d"
done > "$OUT/tc_stats.txt" 2>&1

wait "$P1" "$P2" "$P3"

echo "--- call (client1) ---";            tail -n 4 "$OUT/call.txt"
echo "--- call RTT under load ---";       tail -n 2 "$OUT/ping.txt"
echo "--- download (client2) ---";        tail -n 6 "$OUT/download.txt"
echo "--- policy mid-run ---";            cat "$OUT/policy_mid.txt"; echo
echo "--- tc stats mid-run ---";          cat "$OUT/tc_stats.txt"
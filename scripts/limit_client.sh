#!/usr/bin/env bash
# Usage:
#   sudo bash scripts/limit_client.sh <1|2|3> <down_mbit> [up_mbit]
#   sudo bash scripts/limit_client.sh <1|2|3> off
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 ..."
  exit 1
fi

N="${1:-}"
DOWN="${2:-}"
UP="${3:-}"

if [[ ! "$N" =~ ^[1-3]$ || -z "$DOWN" ]]; then
  echo "Usage: $0 <1|2|3> <down_mbit|off> [up_mbit]"
  exit 1
fi

NS="client${N}"
BR_IF="veth-c${N}-br"

if [[ "$DOWN" == "off" ]]; then
  tc qdisc del dev "$BR_IF" root 2>/dev/null || true
  ip netns exec "$NS" tc qdisc del dev eth0 root 2>/dev/null || true
  echo "Removed limits on $NS"
  exit 0
fi

for v in "$DOWN" ${UP:+"$UP"}; do
  if [[ ! "$v" =~ ^[0-9]+$ || "$v" -lt 1 ]]; then
    echo "Speeds must be whole numbers in Mbit/s (got '$v')"
    exit 1
  fi
done

# Download: shape what the bridge sends toward the client.
# The burst grows with the rate so higher limits still work.
tc qdisc replace dev "$BR_IF" root tbf rate "${DOWN}mbit" \
  burst "$((DOWN * 2 + 100))kb" latency 400ms
msg="$NS download limited to ${DOWN} Mbit/s"

# Upload (optional): shape what the client sends, inside its namespace.
if [[ -n "$UP" ]]; then
  ip netns exec "$NS" tc qdisc replace dev eth0 root tbf rate "${UP}mbit" \
    burst "$((UP * 2 + 100))kb" latency 400ms
  msg="$msg, upload limited to ${UP} Mbit/s"
fi

echo "$msg"
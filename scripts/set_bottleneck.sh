#!/usr/bin/env bash
# Simulated home plan: one shared bottleneck on everything the gateway
# sends toward the clients.
# Usage: sudo bash scripts/set_bottleneck.sh <mbit|off>
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 <mbit|off>"
  exit 1
fi

RATE="${1:-}"
if [[ -z "$RATE" ]]; then
  echo "Usage: $0 <mbit|off>"
  exit 1
fi

if [[ "$RATE" == "off" ]]; then
  tc qdisc del dev br-lab root 2>/dev/null || true
  echo "Bottleneck removed"
  exit 0
fi

if [[ ! "$RATE" =~ ^[0-9]+$ || "$RATE" -lt 1 ]]; then
  echo "Rate must be a whole number in Mbit/s"
  exit 1
fi

tc qdisc replace dev br-lab root tbf rate "${RATE}mbit" \
  burst "$((RATE * 2 + 100))kb" latency 50ms
echo "Shared bottleneck: ${RATE} Mbit/s"
#!/usr/bin/env bash
# Apply a shared bottleneck only to the project-owned lab bridge.
# Usage: sudo bash scripts/set_bottleneck.sh <mbit|off>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lab_common.sh
source "${SCRIPT_DIR}/lab_common.sh"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 <mbit|off>"
  exit 1
fi

lab_require_commands ip tc awk grep
ip link show dev "$LAB_BRIDGE" >/dev/null 2>&1 &&
  lab_bridge_owned ||
  lab_die "refusing to shape a bridge not owned by the Experience Budget lab"

RATE="${1:-}"
if [[ -z "$RATE" ]]; then
  echo "Usage: $0 <mbit|off>"
  exit 1
fi

root_qdisc() {
  tc qdisc show dev "$LAB_BRIDGE" |
    awk '$4 == "root" { print $2, $3; exit }'
}

ROOT="$(root_qdisc)"
case "$ROOT" in
  "noqueue 0:"|"tbf eb0:")
    ;;
  *)
    lab_die "refusing to replace unrecognized bridge qdisc"
    ;;
esac

if [[ "$RATE" == "off" ]]; then
  if [[ "$ROOT" == "tbf eb0:" ]]; then
    tc qdisc del dev "$LAB_BRIDGE" root
  fi
  echo "Bottleneck removed from the owned lab bridge"
  exit 0
fi

if [[ ! "$RATE" =~ ^[0-9]+$ || "$RATE" -lt 1 || "$RATE" -gt 100000 ]]; then
  lab_die "rate must be a whole number between 1 and 100000 Mbit/s"
fi

BURST="$((RATE * 2 + 100))"
tc qdisc replace dev "$LAB_BRIDGE" root handle eb0: tbf \
  rate "${RATE}mbit" burst "${BURST}kb" latency 50ms
ACTUAL="$(root_qdisc)"
if [[ "$ACTUAL" != "tbf eb0:" ]] ||
  ! tc qdisc show dev "$LAB_BRIDGE" |
    grep -Eq "rate[[:space:]]+${RATE}Mbit([[:space:]]|$)"; then
  lab_die "bridge qdisc readback did not match the requested bottleneck"
fi
echo "Verified lab bridge bottleneck: ${RATE} Mbit/s"

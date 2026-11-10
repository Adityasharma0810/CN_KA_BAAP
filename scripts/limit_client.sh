#!/usr/bin/env bash
# Usage:
#   sudo bash scripts/limit_client.sh <1..99> <down_mbit> [up_mbit]
#   sudo bash scripts/limit_client.sh <1..99> off
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lab_common.sh
source "${SCRIPT_DIR}/lab_common.sh"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 ..."
  exit 1
fi

lab_require_commands ip tc awk
N="${1:-}"
DOWN="${2:-}"
UP="${3:-}"
[[ "$N" =~ ^[1-9][0-9]?$ ]] || lab_die "client slot must be between 1 and 99"

NS="$(lab_namespace "$N")"
BR_IF="$(lab_gateway_veth "$N")"
lab_namespace_exists "$NS" &&
  lab_namespace_owned "$NS" ||
  lab_die "refusing to shape a namespace not owned by the lab"
ip link show dev "$BR_IF" >/dev/null 2>&1 &&
  lab_interface_owned "$BR_IF" ||
  lab_die "refusing to shape an interface not owned by the lab"
lab_namespace_interface_owned "$NS" eth0 ||
  lab_die "refusing to shape an unowned namespace interface"

host_root_qdisc() {
  tc qdisc show dev "$BR_IF" | awk '$4 == "root" { print $2, $3; exit }'
}

client_root_qdisc() {
  ip netns exec "$NS" tc qdisc show dev eth0 |
    awk '$4 == "root" { print $2, $3; exit }'
}

HOST_ROOT="$(host_root_qdisc)"
CLIENT_ROOT="$(client_root_qdisc)"
for root in "$HOST_ROOT" "$CLIENT_ROOT"; do
  case "$root" in
    "noqueue 0:"|"tbf eb1:")
      ;;
    *)
      lab_die "refusing to replace an unrecognized client qdisc"
      ;;
  esac
done

if [[ "$DOWN" == "off" ]]; then
  if [[ "$HOST_ROOT" == "tbf eb1:" ]]; then
    tc qdisc del dev "$BR_IF" root
  fi
  if [[ "$CLIENT_ROOT" == "tbf eb1:" ]]; then
    ip netns exec "$NS" tc qdisc del dev eth0 root
  fi
  echo "Client ${N} limits removed"
  exit 0
fi

[[ "$DOWN" =~ ^[0-9]+$ && "$DOWN" -ge 1 && "$DOWN" -le 100000 ]] ||
  lab_die "download rate must be a whole number between 1 and 100000 Mbit/s"
if [[ -n "$UP" ]]; then
  [[ "$UP" =~ ^[0-9]+$ && "$UP" -ge 1 && "$UP" -le 100000 ]] ||
    lab_die "upload rate must be a whole number between 1 and 100000 Mbit/s"
fi

BURST="$((DOWN * 2 + 100))"
tc qdisc replace dev "$BR_IF" root handle eb1: tbf \
  rate "${DOWN}mbit" burst "${BURST}kb" latency 400ms
tc qdisc show dev "$BR_IF" |
  grep -Eq "qdisc tbf eb1: root.*rate[[:space:]]+${DOWN}Mbit" ||
  lab_die "download qdisc readback did not match"

if [[ -n "$UP" ]]; then
  BURST="$((UP * 2 + 100))"
  ip netns exec "$NS" tc qdisc replace dev eth0 root handle eb1: tbf \
    rate "${UP}mbit" burst "${BURST}kb" latency 400ms
  ip netns exec "$NS" tc qdisc show dev eth0 |
    grep -Eq "qdisc tbf eb1: root.*rate[[:space:]]+${UP}Mbit" ||
    lab_die "upload qdisc readback did not match"
else
  if [[ "$CLIENT_ROOT" == "tbf eb1:" ]]; then
    ip netns exec "$NS" tc qdisc del dev eth0 root
  fi
fi

echo "Verified client ${N} download limit: ${DOWN} Mbit/s${UP:+, upload limit: ${UP} Mbit/s}"

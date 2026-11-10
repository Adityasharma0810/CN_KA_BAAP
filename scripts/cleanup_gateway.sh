#!/usr/bin/env bash
# Removes only resources created and owned by the Experience Budget lab.
# Safe to run repeatedly. Usage:
#   sudo bash scripts/cleanup_gateway.sh [client_count]
#   EB_LAB_CLIENTS=5 sudo bash scripts/cleanup_gateway.sh
#   bash scripts/cleanup_gateway.sh --check [client_count]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lab_common.sh
source "${SCRIPT_DIR}/lab_common.sh"

CHECK_ONLY=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK_ONLY=1
  shift
fi

COUNT=""
if [[ -n "${1:-}" ]]; then
  COUNT="$(lab_resolve_count "$1")"
  lab_validate_names "$COUNT"
fi

if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "Cleanup configuration valid${COUNT:+ for ${COUNT} client(s)}."
  exit 0
fi

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 [client_count]"
  exit 1
fi

lab_require_commands ip sysctl awk grep

# Namespaces: union of recorded ownership, currently visible names, and the
# optional requested count. Only names carrying a project marker/state are
# deleted; unrelated namespaces with the same naming style are left alone.
mapfile -t namespaces < <(
  {
    lab_state_list namespace
    ip netns list 2>/dev/null | awk '{ print $1 }' || true
    if [[ -n "$COUNT" ]]; then
      for ((i = 1; i <= COUNT; i++)); do
        lab_namespace "$i"
      done
    fi
  } | awk '/^client[1-9][0-9]*$/' | sort -u
)

for ns in "${namespaces[@]}"; do
  if lab_namespace_exists "$ns" && lab_namespace_owned "$ns"; then
    ip netns del "$ns" 2>/dev/null || true
    echo "Removed namespace ${ns}"
  fi
done

# Host-side veth ends (normally removed with their namespace, but repair any
# orphan left by an interrupted run). Only delete interfaces we own.
mapfile -t veths < <(
  {
    lab_state_list veth
    ls -1 /sys/class/net 2>/dev/null | grep -E '^veth-c[1-9][0-9]*-br$' || true
  } | sort -u
)

for dev in "${veths[@]}"; do
  if ip link show dev "$dev" >/dev/null 2>&1 && lab_interface_owned "$dev"; then
    ip link del "$dev" 2>/dev/null || true
    echo "Removed interface ${dev}"
  fi
done

if ip link show dev "$LAB_BRIDGE" >/dev/null 2>&1 && lab_bridge_owned; then
  ip link del "$LAB_BRIDGE" 2>/dev/null || true
  echo "Removed bridge ${LAB_BRIDGE}"
fi

if nft list table ip "$LAB_NAT_TABLE" >/dev/null 2>&1 && lab_nat_owned; then
  nft delete table ip "$LAB_NAT_TABLE" 2>/dev/null || true
  echo "Removed NAT table ${LAB_NAT_TABLE}"
fi

# DNS directories, but only those carrying our ownership marker/state.
mapfile -t dns_dirs < <(
  {
    lab_state_list dns
    for directory in /etc/netns/client*; do
      if [[ -d "$directory" ]]; then
        printf '%s\n' "$directory"
      fi
    done
  } | sort -u
)

for directory in "${dns_dirs[@]}"; do
  ns="$(basename "$directory")"
  [[ "$ns" =~ ^client[1-9][0-9]*$ ]] || continue
  if lab_dns_owned "$ns"; then
    rm -rf "$directory"
    echo "Removed DNS configuration for ${ns}"
  fi
done

# Restore the forwarding setting only if this project changed it.
PREVIOUS_FORWARD="$(lab_state_list sysctl | awk -F= '$1 == "ip_forward" { print $2; exit }')"
if [[ -n "$PREVIOUS_FORWARD" ]]; then
  sysctl -qw "net.ipv4.ip_forward=${PREVIOUS_FORWARD}" 2>/dev/null || true
  echo "Restored net.ipv4.ip_forward=${PREVIOUS_FORWARD}"
fi

rm -f "$LAB_STATE_FILE"
rmdir "$LAB_STATE_DIR" 2>/dev/null || true
echo "Lab removed."

#!/usr/bin/env bash
# Creates the Experience Budget lab: one bridge plus a configurable number of
# simulated clients. Default: 3 clients. Usage:
#   sudo bash scripts/setup_gateway.sh [client_count]
#   EB_LAB_CLIENTS=5 sudo bash scripts/setup_gateway.sh
#   bash scripts/setup_gateway.sh --check [client_count]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lab_common.sh
source "${SCRIPT_DIR}/lab_common.sh"

CHECK_ONLY=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK_ONLY=1
  shift
fi

COUNT="$(lab_resolve_count "${1:-}")"
lab_validate_names "$COUNT"

if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "Configuration valid: ${COUNT} client(s); namespaces client1..client${COUNT}; gateway interfaces veth-c1-br..veth-c${COUNT}-br"
  exit 0
fi

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 [client_count]"
  exit 1
fi

lab_require_commands ip awk grep install

# Validate ownership before changing anything. An existing resource with one
# of our names but no project marker/state is treated as unrelated and refused.
lab_assert_no_conflicts "$COUNT"

lab_state_init

# Bridge (the "switch" all clients plug into).
if ! ip link show dev "$LAB_BRIDGE" >/dev/null 2>&1; then
  ip link add "$LAB_BRIDGE" type bridge
  echo "Created bridge ${LAB_BRIDGE} (${LAB_PREFIX}.1)"
else
  echo "Reusing bridge ${LAB_BRIDGE}"
fi
ip link set dev "$LAB_BRIDGE" alias "$LAB_MARKER"
ip addr replace "${LAB_PREFIX}.1/24" dev "$LAB_BRIDGE"
ip link set dev "$LAB_BRIDGE" up
lab_state_ensure bridge "$LAB_BRIDGE"

# Clients (each is a network namespace joined to the bridge by a veth cable).
for ((i = 1; i <= COUNT; i++)); do
  ns="$(lab_namespace "$i")"
  host_veth="$(lab_host_veth "$i")"
  gateway_veth="$(lab_gateway_veth "$i")"
  address="$(lab_client_address "$i")"

  if ! lab_namespace_exists "$ns"; then
    ip netns add "$ns"
    echo "Created ${ns} (${address})"
  else
    echo "Reusing ${ns}"
  fi
  lab_state_ensure namespace "$ns"

  install -d -m 0755 "/etc/netns/${ns}"
  printf '%s\n' "$LAB_OWNER" > "/etc/netns/${ns}/.eb-owned"
  lab_state_ensure dns "/etc/netns/${ns}"

  if ! ip netns exec "$ns" ip link show dev eth0 >/dev/null 2>&1; then
    # Remove only project-owned stale ends before rebuilding the cable.
    if ip link show dev "$host_veth" >/dev/null 2>&1; then
      lab_interface_owned "$host_veth" || \
        lab_die "interface ${host_veth} exists but is not owned by ${LAB_OWNER}"
      ip link del "$host_veth"
    fi
    if ip link show dev "$gateway_veth" >/dev/null 2>&1; then
      lab_interface_owned "$gateway_veth" || \
        lab_die "interface ${gateway_veth} exists but is not owned by ${LAB_OWNER}"
      ip link del "$gateway_veth"
    fi
    ip link add "$host_veth" type veth peer name "$gateway_veth"
    ip link set "$host_veth" netns "$ns" name eth0
    echo "Created veth pair for ${ns}"
  fi

  # Repair a namespace whose eth0 survived while its host-side peer disappeared.
  if ! ip link show dev "$gateway_veth" >/dev/null 2>&1; then
    ip netns exec "$ns" ip link del eth0 2>/dev/null || true
    ip link add "$host_veth" type veth peer name "$gateway_veth"
    ip link set "$host_veth" netns "$ns" name eth0
    echo "Repaired veth pair for ${ns}"
  fi

  ip link set dev "$gateway_veth" alias "$LAB_MARKER"
  ip link set dev "$gateway_veth" master "$LAB_BRIDGE"
  ip link set dev "$gateway_veth" up
  lab_state_ensure veth "$gateway_veth"

  ip netns exec "$ns" ip link set dev eth0 alias "$LAB_MARKER"
  ip netns exec "$ns" ip addr replace "${address}/24" dev eth0
  ip netns exec "$ns" ip link set dev eth0 up
  ip netns exec "$ns" ip link set dev lo up
  ip netns exec "$ns" ip route replace default via "${LAB_PREFIX}.1"

  # DNS for each client (ip netns exec reads /etc/netns/<name>/resolv.conf).
  printf 'nameserver 1.1.1.1\n' > "/etc/netns/${ns}/resolv.conf"
done

# The lab is intentionally isolated. Do not enable forwarding or NAT through
# the host's default route; namespace-to-namespace experiments need only the
# project-owned bridge.
echo "Lab ready: ${COUNT} isolated client(s); host uplink unchanged."

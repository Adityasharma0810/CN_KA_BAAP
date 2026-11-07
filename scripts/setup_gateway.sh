#!/usr/bin/env bash
# Creates the Experience Budget lab: one bridge + 3 simulated clients.
set -euo pipefail

BRIDGE="br-lab"
PREFIX="10.50.0"
CLIENTS=(1 2 3)

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

# Bridge (the "switch" all clients plug into)
if ! ip link show "$BRIDGE" &>/dev/null; then
  ip link add "$BRIDGE" type bridge
  ip addr add "${PREFIX}.1/24" dev "$BRIDGE"
  ip link set "$BRIDGE" up
  echo "Created bridge $BRIDGE (${PREFIX}.1)"
fi

# Clients (each is a network namespace joined to the bridge by a veth cable)
for i in "${CLIENTS[@]}"; do
  ns="client${i}"
  if ip netns list | grep -qw "$ns"; then
    echo "Skipping $ns (already exists)"
    continue
  fi
  ip netns add "$ns"
  ip link add "veth-c${i}" type veth peer name "veth-c${i}-br"
  ip link set "veth-c${i}" netns "$ns" name eth0
  ip link set "veth-c${i}-br" master "$BRIDGE"
  ip link set "veth-c${i}-br" up
  ip netns exec "$ns" ip addr add "${PREFIX}.1${i}/24" dev eth0
  ip netns exec "$ns" ip link set eth0 up
  ip netns exec "$ns" ip link set lo up
  ip netns exec "$ns" ip route add default via "${PREFIX}.1"
  echo "Created $ns (${PREFIX}.1${i})"
done
# DNS for each client (ip netns exec reads /etc/netns/<name>/resolv.conf)
for i in "${CLIENTS[@]}"; do
  mkdir -p "/etc/netns/client${i}"
  echo "nameserver 1.1.1.1" > "/etc/netns/client${i}/resolv.conf"
done

# Internet access: forward + NAT out through the VM's default interface
UPLINK=$(ip route show default | awk '{print $5; exit}')
sysctl -qw net.ipv4.ip_forward=1
nft delete table ip eb_nat 2>/dev/null || true
nft add table ip eb_nat
nft add chain ip eb_nat postrouting '{ type nat hook postrouting priority 100; }'
nft add rule ip eb_nat postrouting ip saddr ${PREFIX}.0/24 oifname "$UPLINK" masquerade
echo "NAT enabled via $UPLINK"
echo "Lab ready."
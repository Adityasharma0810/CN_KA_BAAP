#!/usr/bin/env bash
# Removes the Experience Budget lab. Safe to run repeatedly.
if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

for i in 1 2 3; do
  ip netns del "client${i}" 2>/dev/null || true
  rm -rf "/etc/netns/client${i}"
done
ip link del br-lab 2>/dev/null || true
nft delete table ip eb_nat 2>/dev/null || true
echo "Lab removed."
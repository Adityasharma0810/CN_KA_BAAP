#!/usr/bin/env bash
# Installs a root-owned copy of limit_client.sh and lets the calling
# user run only that file via sudo without a password.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

API_USER="${SUDO_USER:?run this through sudo}"
SRC="$(dirname "$(readlink -f "$0")")/limit_client.sh"
DEST="/usr/local/sbin/eb-limit-client"
RULE="/etc/sudoers.d/experience-budget"

install -o root -g root -m 755 "$SRC" "$DEST"

echo "${API_USER} ALL=(root) NOPASSWD: ${DEST} *" > "${RULE}.tmp"
chmod 440 "${RULE}.tmp"
visudo -cf "${RULE}.tmp"
mv "${RULE}.tmp" "$RULE"

echo "Installed $DEST for user $API_USER"
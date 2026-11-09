#!/usr/bin/env bash
set -euo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

if [[ "$EUID" -ne 0 ]]; then
  printf 'Run this script with sudo.\n' >&2
  exit 1
fi

readonly DEST_HELPER=/usr/local/libexec/eb/eb-priv
readonly SUDOERS_FILE=/etc/sudoers.d/eb-priv
readonly LAB_STATE_FILE=/run/experience-budget/lab.state
readonly SAVED_BOTTLENECK=/run/experience-budget/eb-priv/bottleneck-original
if [[ -x "$DEST_HELPER" ]] &&
  /usr/bin/grep -q 'traffic_command()' "$DEST_HELPER"; then
  "$DEST_HELPER" traffic stop-all >/dev/null
  if [[ -r "$LAB_STATE_FILE" ]]; then
    "$DEST_HELPER" bottleneck off >/dev/null
  elif [[ -e "$SAVED_BOTTLENECK" ]]; then
    printf 'Cannot restore the saved bottleneck without the lab state file.\n' >&2
    exit 1
  fi
  printf 'Stopped helper-owned traffic and restored the bottleneck.\n'
fi
/usr/bin/rm -f -- "$SUDOERS_FILE" "$DEST_HELPER"
/usr/bin/rmdir --ignore-fail-on-non-empty /usr/local/libexec/eb 2>/dev/null || true
printf 'Removed the eb-priv helper and sudo rule.\n'

#!/usr/bin/env bash
set -euo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

if [[ "$EUID" -ne 0 || -z "${SUDO_USER:-}" ]]; then
  printf 'Run with sudo from a user account.\n' >&2
  exit 1
fi

if [[ ! "$SUDO_USER" =~ ^[a-z_][a-z0-9_.-]*$ ]] ||
  ! /usr/bin/id "$SUDO_USER" >/dev/null 2>&1; then
  printf 'Unsupported sudo user.\n' >&2
  exit 1
fi

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly DEST_DIR=/usr/local/libexec/eb
readonly DEST_HELPER="${DEST_DIR}/eb-priv"
# Sudoers file name sorts after any broad password rule (e.g. experience-budget)
# so the NOPASSWD entries are the last match and actually take effect.
readonly SUDOERS_FILE=/etc/sudoers.d/zz-eb-priv
readonly SUDOERS_TMP="${SUDOERS_FILE}.tmp"
readonly HELPER_TMP="${DEST_DIR}/eb-priv.tmp"

cleanup() {
  /usr/bin/rm -f -- "$SUDOERS_TMP" "$HELPER_TMP"
}
trap cleanup EXIT

if [[ -L "$DEST_DIR" ]]; then
  printf 'Privileged helper directory is not safely owned.\n' >&2
  exit 1
fi
/usr/bin/install -d -o root -g root -m 0755 "$DEST_DIR"
if [[ -L "$DEST_DIR" ]] ||
  [[ "$(/usr/bin/stat -c '%U:%G:%a' "$DEST_DIR")" != root:root:755 ]]; then
  printf 'Privileged helper directory is not safely owned.\n' >&2
  exit 1
fi

/usr/bin/install -o root -g root -m 0755 \
  "${SCRIPT_DIR}/eb-priv" "$HELPER_TMP"
{
  printf '%s ALL=(root) NOPASSWD: %s probe [1-9]\n' "$SUDO_USER" "$DEST_HELPER"
  for slot_pattern in '[1-9]' '[1-9][0-9]'; do
    for profile in call game stream bulk; do
      for seconds_pattern in '[5-9]' '[1-9][0-9]' '1[01][0-9]' 120; do
        printf '%s ALL=(root) NOPASSWD: %s traffic start %s %s %s\n' \
          "$SUDO_USER" "$DEST_HELPER" "$slot_pattern" "$profile" "$seconds_pattern"
      done
    done
    printf '%s ALL=(root) NOPASSWD: %s traffic stop %s\n' \
      "$SUDO_USER" "$DEST_HELPER" "$slot_pattern"
  done
  printf '%s ALL=(root) NOPASSWD: %s traffic stop-all\n' "$SUDO_USER" "$DEST_HELPER"
  for rate in 100 50 20 10 5 off; do
    printf '%s ALL=(root) NOPASSWD: %s bottleneck %s\n' \
      "$SUDO_USER" "$DEST_HELPER" "$rate"
  done
} > "$SUDOERS_TMP"
/usr/bin/chown root:root "$SUDOERS_TMP"
/usr/bin/chmod 0440 "$SUDOERS_TMP"
/usr/sbin/visudo -cf "$SUDOERS_TMP" >/dev/null

/usr/bin/mv -f -- "$HELPER_TMP" "$DEST_HELPER"
/usr/bin/mv -f -- "$SUDOERS_TMP" "$SUDOERS_FILE"
# Remove the legacy sudoers file name (sorted before the broad password rule
# and so overridden by it). Fixed path; safe to remove as we own it.
/usr/bin/rm -f -- /etc/sudoers.d/eb-priv 2>/dev/null || true
printf 'Installed root-owned lab helper and bounded sudo rules for %s.\n' "$SUDO_USER"

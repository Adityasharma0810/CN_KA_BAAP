#!/usr/bin/env bash
# Shared configuration, validation, ownership, and state helpers for the
# project-owned Experience Budget namespace lab. Source this file; do not run it.

LAB_BRIDGE="${EB_LAB_BRIDGE:-br-lab}"
LAB_PREFIX="${EB_LAB_PREFIX:-10.50.0}"
LAB_NAT_TABLE="${EB_LAB_NAT_TABLE:-eb_nat}"
LAB_OWNER="experience-budget"
LAB_MARKER="experience-budget-lab"
LAB_STATE_DIR="${EB_LAB_STATE_DIR:-/run/experience-budget}"
LAB_STATE_FILE="${LAB_STATE_DIR}/lab.state"
DEFAULT_CLIENTS=3
MAX_CLIENTS=99

lab_die() {
  echo "ERROR: $*" >&2
  exit 1
}

lab_validate_count() {
  local count="${1:-}"
  [[ "$count" =~ ^[1-9][0-9]*$ ]] || lab_die "client count must be a positive integer (got '${count}')"
  (( count <= MAX_CLIENTS )) || lab_die "client count must be between 1 and ${MAX_CLIENTS} (got '${count}')"
}

lab_resolve_count() {
  local requested="${1:-}"
  local count
  if [[ -n "$requested" ]]; then
    count="$requested"
  else
    count="${EB_LAB_CLIENTS:-$DEFAULT_CLIENTS}"
  fi
  lab_validate_count "$count"
  printf '%s\n' "$count"
}

lab_namespace() {
  printf 'client%s\n' "$1"
}

lab_host_veth() {
  printf 'veth-c%s\n' "$1"
}

lab_gateway_veth() {
  printf 'veth-c%s-br\n' "$1"
}

lab_client_address() {
  printf '%s.%s\n' "$LAB_PREFIX" "$((10 + $1))"
}

lab_validate_names() {
  local count="$1"
  local i ns host_veth gateway_veth address

  [[ "$LAB_BRIDGE" =~ ^[A-Za-z0-9_.-]{1,15}$ ]] || lab_die "invalid bridge name: ${LAB_BRIDGE}"
  [[ "$LAB_PREFIX" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || lab_die "invalid IPv4 prefix: ${LAB_PREFIX}"
  [[ "$LAB_NAT_TABLE" =~ ^[A-Za-z0-9_.-]{1,32}$ ]] || lab_die "invalid NAT table name: ${LAB_NAT_TABLE}"

  for ((i = 1; i <= count; i++)); do
    ns="$(lab_namespace "$i")"
    host_veth="$(lab_host_veth "$i")"
    gateway_veth="$(lab_gateway_veth "$i")"
    address="$(lab_client_address "$i")"

    [[ "$ns" =~ ^client[1-9][0-9]*$ ]] || lab_die "invalid namespace name: ${ns}"
    [[ "$host_veth" =~ ^veth-c[1-9][0-9]*$ ]] || lab_die "invalid host interface name: ${host_veth}"
    [[ "$gateway_veth" =~ ^veth-c[1-9][0-9]*-br$ ]] || lab_die "invalid gateway interface name: ${gateway_veth}"
    (( ${#host_veth} <= 15 )) || lab_die "host interface name is too long: ${host_veth}"
    (( ${#gateway_veth} <= 15 )) || lab_die "gateway interface name is too long: ${gateway_veth}"
    [[ "$host_veth" != "$LAB_BRIDGE" && "$gateway_veth" != "$LAB_BRIDGE" ]] || \
      lab_die "generated interface collides with bridge: ${LAB_BRIDGE}"
    [[ "$address" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || \
      lab_die "invalid client address: ${address}"
  done
}

lab_require_commands() {
  local command_name
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || \
      lab_die "required command not found: ${command_name}"
  done
}

lab_state_init() {
  install -d -m 0755 "$LAB_STATE_DIR"
  if [[ ! -f "$LAB_STATE_FILE" ]]; then
    printf 'version 1\nowner %s\n' "$LAB_OWNER" > "$LAB_STATE_FILE"
  fi
}

lab_state_ensure() {
  local kind="$1"
  local name="$2"
  lab_state_init
  grep -qxF "${kind} ${name}" "$LAB_STATE_FILE" 2>/dev/null || \
    printf '%s %s\n' "$kind" "$name" >> "$LAB_STATE_FILE"
}

lab_state_has() {
  local kind="$1"
  local name="$2"
  [[ -f "$LAB_STATE_FILE" ]] && grep -qxF "${kind} ${name}" "$LAB_STATE_FILE" >/dev/null 2>&1
}

lab_state_list() {
  local kind="$1"
  [[ -f "$LAB_STATE_FILE" ]] || return 0
  awk -v kind="$kind" '$1 == kind { $1=""; sub(/^[[:space:]]+/, ""); print }' "$LAB_STATE_FILE"
}

lab_interface_alias() {
  local dev="$1"
  ip -d link show dev "$dev" 2>/dev/null | awk '$1 == "alias" { print $2; exit }'
}

lab_interface_owned() {
  local dev="$1"
  [[ "$(lab_interface_alias "$dev")" == "$LAB_MARKER" ]] && return 0
  lab_state_has veth "$dev"
}

lab_bridge_owned() {
  [[ "$(lab_interface_alias "$LAB_BRIDGE")" == "$LAB_MARKER" ]] && return 0
  lab_state_has bridge "$LAB_BRIDGE"
}

lab_namespace_exists() {
  local ns="$1"
  ip netns list 2>/dev/null | awk '{ print $1 }' | grep -qxF "$ns"
}

lab_namespace_owned() {
  local ns="$1"
  lab_state_has namespace "$ns" && return 0
  [[ -f "/etc/netns/${ns}/.eb-owned" ]]
}

lab_dns_owned() {
  local ns="$1"
  [[ -f "/etc/netns/${ns}/.eb-owned" ]] && return 0
  lab_state_has dns "/etc/netns/${ns}"
}

lab_nat_owned() {
  lab_state_has nft "$LAB_NAT_TABLE" && return 0
  nft list table ip "$LAB_NAT_TABLE" 2>/dev/null | grep -qF "$LAB_MARKER"
}

lab_assert_no_conflicts() {
  local count="$1"
  local i ns host_veth gateway_veth

  if ip link show dev "$LAB_BRIDGE" >/dev/null 2>&1; then
    lab_bridge_owned || \
      lab_die "bridge ${LAB_BRIDGE} exists but is not owned by ${LAB_OWNER}"
  fi

  for ((i = 1; i <= count; i++)); do
    ns="$(lab_namespace "$i")"
    host_veth="$(lab_host_veth "$i")"
    gateway_veth="$(lab_gateway_veth "$i")"

    if lab_namespace_exists "$ns"; then
      lab_namespace_owned "$ns" || \
        lab_die "namespace ${ns} exists but is not owned by ${LAB_OWNER}"
    fi
    if ip link show dev "$host_veth" >/dev/null 2>&1; then
      lab_interface_owned "$host_veth" || \
        lab_die "interface ${host_veth} exists but is not owned by ${LAB_OWNER}"
    fi
    if ip link show dev "$gateway_veth" >/dev/null 2>&1; then
      lab_interface_owned "$gateway_veth" || \
        lab_die "interface ${gateway_veth} exists but is not owned by ${LAB_OWNER}"
    fi
    if [[ -d "/etc/netns/${ns}" ]] && ! lab_dns_owned "$ns"; then
      lab_die "DNS directory /etc/netns/${ns} exists but is not owned by ${LAB_OWNER}"
    fi
  done

  if nft list table ip "$LAB_NAT_TABLE" >/dev/null 2>&1; then
    lab_nat_owned || \
      lab_die "NAT table ${LAB_NAT_TABLE} exists but is not owned by ${LAB_OWNER}"
  fi
}

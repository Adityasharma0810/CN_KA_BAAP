# Restricted privileged lab helper

## Why it exists

The namespace lab requires root to enter client namespaces and alter the
shared lab bridge qdisc. The web application must not be able to run arbitrary
root commands. `eb-priv` is the only sudo target and exposes a fixed allow-list:
bounded ICMP probes, bounded iperf traffic profiles, and five fixed bottleneck
rates plus `off`.

All helper commands use fixed executable paths, validate arguments again
inside the helper, suppress tool output, and return fixed status lines. There
is no shell command, `eval`, user-supplied path, destination, interface, or
process identifier accepted by the API.

## Exact threat model

The installer grants the invoking user only `/usr/local/libexec/eb/eb-priv`.
The generated rules allow:

```sudoers
<SUDO_USER> ALL=(root) NOPASSWD: /usr/local/libexec/eb/eb-priv probe [1-9]
<SUDO_USER> ALL=(root) NOPASSWD: /usr/local/libexec/eb/eb-priv traffic start [1-9] call [5-9]
<SUDO_USER> ALL=(root) NOPASSWD: /usr/local/libexec/eb/eb-priv traffic stop-all
<SUDO_USER> ALL=(root) NOPASSWD: /usr/local/libexec/eb/eb-priv bottleneck 20
```

The installer expands the traffic start and stop patterns only over slots
`[1-9]` and `[1-9][0-9]`, the four literal profiles `call`, `game`, `stream`,
`bulk`, and exact duration patterns covering 5 through 120 seconds. Bottleneck
rules are only `100`, `50`, `20`, `10`, `5`, and `off`. It validates the full
temporary sudoers file with `visudo -cf` before installing it mode `0440`.
The helper and containing directory are root-owned and not writable by the
application user.

If the web application is compromised, the attacker can send bounded ICMP
probes; start one of the four fixed traffic profiles in a configured lab
namespace for 5–120 seconds; stop only helper-tracked traffic; and apply only
the five fixed rates to the configured lab bridge. The helper restores a
pre-scenario `noqueue` state or the exact TBF shape produced by
`scripts/set_bottleneck.sh`. If it sees an unsupported pre-existing qdisc, it
fails closed instead of overwriting it.

The attacker cannot run arbitrary root commands, choose an arbitrary
destination or executable, change other interfaces, signal arbitrary
processes, choose an unbounded traffic duration, alter files outside the
helper's private runtime directory, or use any subcommand not explicitly
listed above. ICMP results describe network-layer RTT, RTT variation, and
ICMP loss—not application-level latency or loss.

The helper derives the bridge and gateway from the existing lab state and live
bridge configuration. It validates configured slots against the state file
and live namespace list. The runtime pid and bottleneck state files are kept
in root-only `/run/experience-budget/eb-priv`.

## Install and re-install

Install or re-install after a helper change:

```bash
sudo bash scripts/privileged/install_eb_priv.sh
```

The installer requires root and a valid `SUDO_USER`. It copies the helper to
`/usr/local/libexec/eb/eb-priv` as `root:root`, mode `0755`, and installs the
validated sudoers file as `root:root`, mode `0440`. Do not edit the installed
helper or sudoers file manually.

## Verify

Verify the existing probe permission:

```bash
sudo -n /usr/local/libexec/eb/eb-priv probe 1
```

Scenario traffic and bottleneck commands are invoked by the backend with
`sudo -n`; they return only fixed `ok ...` or `fail <code>` lines. No raw
ping/iperf output, network address, interface name, namespace name, or path is
returned to the API.

## Uninstall

```bash
sudo bash scripts/privileged/uninstall_eb_priv.sh
```

This removes the installed helper and sudoers file, not the lab or its
configuration. Before removal, it asks the installed helper to stop its
tracked traffic and restore the saved bottleneck state.

## Adding a subcommand safely

Add a fixed helper `case` branch, independently validate each argument, use
absolute executable paths, emit a bounded fixed-format result, and ensure the
operation cannot affect resources outside the lab. Add only exact sudoers
argument patterns for the new forms and validate the generated file with
`visudo -cf`. Add unprivileged bad-input tests and fake-runner service tests.
Never add a generic command runner, shell evaluation, wildcard command, or
user-supplied executable/path.

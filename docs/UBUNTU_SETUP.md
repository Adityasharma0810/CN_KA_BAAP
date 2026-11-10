# Ubuntu namespace-lab setup

## Safety and support boundary

The lab is for isolated namespace-to-namespace traffic only. Setup does not
enable host IP forwarding, install NAT, or route test traffic through the
machine's default uplink. It changes only project-created bridge, namespace,
and veth resources. It is not a physical router or household-device test.

Current scripts still use stable names (`br-lab`, `clientN`, and
`veth-cN-br`), not per-run randomized names. Setup refuses a colliding resource
unless the project state/marker identifies it as lab-owned. Do not run multiple
instances concurrently or use this configuration on a shared host.

## Requirements

- Ubuntu 24.04 or newer and a supported Linux kernel with network namespaces,
  veth, and bridge support.
- `iproute2` (`ip`, `tc`, `bridge`), `awk`, `grep`, and `install`.
- Root privileges and effective `CAP_NET_ADMIN` for namespace, bridge, veth,
  and qdisc changes.
- Python dependencies from the repository requirements for the API and tests.
- `iperf3` is optional for existing traffic scenarios; it was not present in
  the inspected VM.

## Inspect before setup

On the dedicated Ubuntu lab host, record OS/kernel/Python, tool versions,
interfaces/default route, namespaces, bridges, and exact target resources.
Confirm the target names are unused or project-owned. Never target a physical
uplink.

Validate without changing networking:

```bash
bash scripts/setup_gateway.sh --check 3
bash scripts/setup_gateway.sh --check 5
bash scripts/cleanup_gateway.sh --check 3
```

Create the lab (not run in this execution because the VM has no
`CAP_NET_ADMIN`):

```bash
sudo bash scripts/setup_gateway.sh 3
# Or:
sudo bash scripts/setup_gateway.sh 5
```

The namespaces can communicate on the lab bridge. They intentionally do not
have internet/NAT access. Generate local test traffic only between lab
namespaces or the lab gateway.

Cleanup only after confirming the state file and ownership markers refer to
this project lab:

```bash
sudo bash scripts/cleanup_gateway.sh 3
sudo bash scripts/cleanup_gateway.sh 3
```

The cleanup script is intended to be repeatable and removes project-marked
resources; inspect any legacy `/run/experience-budget/lab.state` entries before
cleaning a lab created by older revisions. Cleanup must not be used as a host
network reset.

## Current execution result

Configuration-only checks passed for three and five clients. Native setup and
cleanup did not run: `ip netns add eb-capability-probe` returned
`Operation not permitted` before creating a namespace. The original host route
and interfaces remained present. See `UBUNTU_TEST_RESULTS.md` and
`UBUNTU_LIMITATIONS.md`.

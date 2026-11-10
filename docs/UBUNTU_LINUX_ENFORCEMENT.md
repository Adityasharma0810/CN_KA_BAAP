# Linux traffic enforcement

## Implemented code paths

The `qos/` package provides validated capacity-bounded per-client plans,
read-only capability detection, shell-free bounded command execution,
CAKE/HTB+fq_codel command construction, upload redirection to IFB, kernel
readback parsing, and a lifecycle facade with ownership checks and rollback
reporting.

- CAKE is preferred only when detected. It is a per-interface shaper; this lab
  maps one lab-owned gateway-side veth per anonymous client, so CAKE can enforce
  each client's ceiling on its own veth.
- HTB + fq_codel is the documented fallback and also creates a per-client
  hierarchy on each client veth.
- Upload uses ingress on the lab-owned veth, `matchall` + `mirred` redirect to
  a separately owned IFB, then the selected root qdisc on that IFB.
- Explicit CAKE/HTB requests fail when unsupported. The code does not claim
  success until qdisc/class/filter readback matches.
- No command targets the physical host uplink. The existing lab `TBF` scripts
  remain a legacy path and now validate ownership, a reserved qdisc handle,
  and rate readback.
- Complex pre-existing qdiscs are not reconstructed approximately by rollback;
  the implementation refuses those states. This deliberately limits rollback
  to the unshaped default until full snapshots are available.

## Capability and test evidence

Read-only inspection found `tc`/`iproute2` 6.19.0, `fq_codel` present on the
host uplink, and kernel module indexes on disk. CAKE, HTB, IFB, matchall, and
mirred were not loaded under `/sys/module` at inspection. The module detector
also checks module indexes, but capability presence is not proof of a usable
qdisc. No qdisc was applied because the VM lacks `CAP_NET_ADMIN`.

Unit evidence covers command construction, mode detection/fallback, allocation
bounds, unsupported modes, ownership refusal, readback parsing, and readback
errors. No CAKE or HTB+fq_codel live qdisc test, upload test, throughput check,
or rollback test has passed in this execution. See
`UBUNTU_TEST_RESULTS.md`.

## Safe operating procedure

1. Use only a newly created, ownership-marked lab veth/IFB.
2. Read and save qdisc state before modification. The current implementation
   refuses non-default pre-existing qdisc state.
3. Apply a plan only after checking per-direction allocation totals against
   available capacity.
4. Read back root qdiscs, rates, HTB leaves, ingress filter, and IFB state.
5. On a partial failure, inspect rollback status; `rollback_ok=false` or an
   unverified state is unhealthy, not restored.
6. Cleanup only the exact lab interfaces and IFBs owned by the active run.

Do not treat simulated namespace rates as household Wi-Fi performance or
physical client allocations.

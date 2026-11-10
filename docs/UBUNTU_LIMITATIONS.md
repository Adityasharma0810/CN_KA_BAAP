# Ubuntu/Linux limitations and blockers

## Current VM constraints

- Ubuntu 26.04.1 LTS, kernel 7.0.0-42-generic, Python 3.14.4.
- Current user has no effective capabilities. Namespace creation failed with
  `Operation not permitted`; `CAP_NET_ADMIN` is unavailable.
- `iperf3` is not installed.
- The default route is through the existing virtual adapter. The adapter,
  default route, firewall, and host qdisc were not changed.
- The kernel has module indexes available. Some qdisc modules were not loaded;
  a detected module file alone does not prove that the kernel can load or apply
  the feature.
- The gateway endpoint can be unit-tested, but the Linux lab source is absent,
  and no Windows host or second VM was connected for real gateway transport.

## Incomplete acceptance

- Native three/five namespace setup and cleanup, client isolation, byte/rate
  direction, simultaneous traffic, idle behavior, disappearance, and counter
  reset remain unverified here.
- CAKE and HTB+fq_codel were not applied to lab-owned interfaces. Upload IFB,
  ingress redirect, shaping rate, qdisc readback, rollback, and cleanup have
  only code/unit coverage.
- The new enforcement abstraction is not wired to the rule-based controller.
  The existing optimizer is not described as a completed QoE optimizer.
- Product topology is based on stored observations/registry state; it is not
  live discovery of namespaces, bridges, veth links, or enforcement points.
- A/B performance and fairness tests were not run. No performance gain is
  claimed.
- Physical phone/laptop attribution, Wi-Fi signal/channel measurements,
  vendor router control, multi-WAN, production deployment readiness, and
  Windows↔Ubuntu connectivity are outside the evidence obtained here.

## Dedicated-VM verification

On a dedicated Ubuntu VM with working namespace permissions, first inspect
network state and only then run the documented isolated lab. Test supported
qdiscs by capability detection and apply only to ownership-marked lab veths;
capture `tc` readback and cleanup verification. Use a private VM network for
the gateway and never expose the agent publicly.

Windows-to-Ubuntu checks are listed in `UBUNTU_GATEWAY_INTEGRATION.md`. They
remain blocked until both machines are available on a private route.

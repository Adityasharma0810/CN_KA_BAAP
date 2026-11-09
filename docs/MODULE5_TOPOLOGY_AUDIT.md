# Module 5 topology evidence audit

## Evidence sources

Topology reads canonical observations through
`observation_query_service.build_current_observations` and reads the public
anonymous records from `lab_accounting_service.registry`. It does not collect
new measurements. A canonical observation is identified by its source, scope,
quality, timestamp, and (only for client scope) opaque client ID.

The shared observation freshness threshold is
`STALE_OBSERVATION_AFTER_SECONDS` (300 seconds). An age of exactly 300 seconds
is fresh; only a greater age is stale. The registry also reports client status
and last-seen time. Its explicit `offline` status is evidence for an anonymous
client only; it is not evidence that the lab or gateway itself is offline.
The registry can produce that status from its timeout policy as well as an
explicit offline mark, and its public record does not distinguish those causes.

## Node evidence and state rules

| Node/source | Evidence that may be shown | What remains unknown |
|---|---|---|
| Application | No application-health observation is stored by Feature 3. It is `missing` until one exists. | Process readiness, deployment status, and application-to-network connectivity. |
| Windows host | Latest `windows_host` / `aggregate_gateway` observation. | Host reachability, interface identity, and any client or physical network attachment. |
| Windows hotspot | Latest `windows_hotspot` / `aggregate_hotspot` observation. It is independent of the Linux lab and is always represented independently. | Hotspot reachability and which clients, if any, used it. |
| Linux gateway/lab | Latest `linux_gateway` aggregate observation and `linux_namespace_lab` / `client` observations. The latter can establish anonymous client measurement membership. | Lab/network reachability as a whole; an aggregate or per-client measurement does not prove a physical route. |
| Anonymous client | Public registry record and matching client-scoped canonical observation. Labels are anonymous; IDs are opaque. Registry `offline` is explicit evidence for that client. | Any real-world identity, address, or attachment to Windows host/hotspot. |

States are selected conservatively:

1. A failed source query or failed registry read is `unavailable`; its exception
   is logged and not returned.
2. No stored observation (or a registered client that has never been observed)
   is `missing`.
3. An anonymous client whose public registry status is `offline` is
   `offline`. This is a registry-reported status, which may be inferred by the
   registry's timeout policy; the data does not establish whether the client
   explicitly disconnected. Aggregate observation quality `unavailable` means
   its collector could not provide data, so it is `unavailable`, not proof
   that the node is offline.
4. An otherwise usable observation older than 300 seconds is `stale`.
5. A fresh observation establishes that data was observed, not that the source
   is currently connected. Because the allowed state enum has no `online` or
   `observed` value, its state remains `unknown`; its timestamp and
   `data_quality` preserve the evidence. Quality `unknown` also yields
   `unknown`. A fresh registry `online` status is represented as `unknown` for
   the same reason.
6. Exactly 300 seconds is fresh. Explicit client `offline` and source failure
   take precedence over timestamp freshness.

The gateway-status response reports application, Windows host, hotspot, and
Linux lab separately. Application has no persisted health evidence today, so
its state is `missing`. Registry failure affects only registry/client evidence;
it does not change observation-derived Windows or lab states.

## Edge evidence

| Candidate edge | Evidence | Output |
|---|---|---|
| Linux lab to anonymous client | A client-scoped `linux_namespace_lab` observation names that opaque client ID. | `observed` edge. |
| Linux lab to registered anonymous client without an observation | The public registry identifies the record as a member of its anonymous lab-client registry, but no measurement establishes activity. | `derived` membership edge, never a physical-link claim. |
| Any other relation between known nodes | No canonical observation or registry field records a physical/configured relationship. | No edge is emitted; the relation remains unknown. |

No current evidence justifies a `configured` edge. An `unknown` edge type is
reserved for a relationship whose existence is established but whose type is
not; the current stored data establishes no such additional relationship.
Application-to-collector monitoring is not a network edge.

## Must never be fabricated

- Do not add a router node: no router identity or router observation is stored.
- Do not infer physical links, adjacency, routing, or configured network
  topology from measurement provenance.
- Windows host and hotspot observations are aggregate-only. They never create
  anonymous client children or per-client attribution.
- A Linux lab/client observation supports only an anonymous measurement
  relationship; it does not prove a physical link or reveal identity.
- Never return IP/MAC addresses, hostnames, namespaces, veth/bridge/interface
  names, adapter names, paths, or raw exceptions.

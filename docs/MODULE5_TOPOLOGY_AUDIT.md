# Module 5 topology evidence audit

## Evidence sources

Feature 5 reads canonical observations through
`observation_query_service.build_current_observations`, the public anonymous
records from `lab_accounting_service.registry`, and application status from
`health_service.build_observation_health().components.application`. The routes
do not collect measurements or probe the network. A failure in a source query,
registry read, or application-health call marks only that source unavailable;
the failure is logged and its details are never returned.

The shared observation freshness threshold is
`STALE_OBSERVATION_AFTER_SECONDS` (300 seconds). Exactly 300 seconds is fresh;
only greater ages are stale.

## Node/source evidence and state rules

| Node/source | Evidence that may be shown | What remains unknown |
|---|---|---|
| Application | The existing health service's `application` component. Healthy maps to `online` with derived quality; an exception maps to `unavailable`. | The health component does not establish application-to-network connectivity. |
| Windows host | Latest `windows_host` / `aggregate_gateway` observation. | Host reachability, interface identity, and any client or physical network attachment. |
| Windows hotspot | Latest `windows_hotspot` / `aggregate_hotspot` observation. It is independent of the Linux lab and always represented independently. | Hotspot reachability and which clients, if any, used it. |
| Linux gateway/lab | Latest `linux_gateway` aggregate observation and `linux_namespace_lab` / `client` observations. The latter identifies only opaque anonymous clients. | Lab reachability and any physical path; no aggregate offline signal exists. |
| Anonymous client | Public registry record and matching client-scoped canonical observation. The client can be online only when the registry says online and a fresh measured/derived observation exists. | Real-world identity, address, physical attachment, or why the registry reports offline. |

Exact state precedence for observation-backed sources is:

1. Failed query, registry read, or application-health call: `unavailable`.
2. Latest observation quality `unavailable`: `unavailable`.
   The gateway-status `linux_lab` category combines Linux aggregate and client
   observations; a failed query in either marks that combined category
   unavailable. Topology source records retain their separate statuses.
3. Anonymous client registry status `offline`: `offline`, even if an observation
   also exists. The registry status can be explicit or timeout-derived; its
   public data does not distinguish the cause.
4. An observation older than 300 seconds: `stale`.
5. A fresh observation with quality `measured` or `derived`: `online` for
   Windows host, hotspot, and Linux lab. For an anonymous client this also
   requires registry status `online`; otherwise the state is `unknown`.
6. A fresh observation with quality `unknown`: `unknown`.
7. No observation: `missing` for observation-backed nodes. Registered client
   metadata by itself does not make the client online; without a client-scoped
   observation its state is `missing`, unless registry status is offline. The
   application is never missing.
8. The application maps healthy to `online`, unavailable to `unavailable`, and
   degraded to `unknown`; it is never reported `missing` when the health call
   succeeds.

`online` means recent measurement or successful application health only. It
does not assert link state or network connectivity. The gateway-status overall
value is `unavailable` if any of the four reported states is unavailable,
`healthy` only if all four are online, and `degraded` otherwise.

## Edge evidence

| Candidate edge | Evidence | Output |
|---|---|---|
| Linux lab to anonymous client | A client-scoped `linux_namespace_lab` observation names that opaque client ID. | `observed` edge. |
| Linux lab to registered anonymous client without an observation | The public registry identifies the anonymous client as a member of its lab registry, but no current measurement exists. | `derived` membership edge, not a physical-link claim. |
| Configured relationship | Would require explicit stored configuration data tying two nodes together. | `configured` enum is reserved; no current source justifies such an edge. |
| Any other relationship | No stored evidence establishes its existence or physical meaning. | No edge is emitted; `unknown` is reserved for an established relation with unknown type. |

The validator rejects duplicate node IDs, edges that reference missing nodes,
duplicate undirected endpoint pairs (including reversed duplicates), and
self-loops. Invalid topology is logged and returned as generic
`503 topology_unavailable`.

## Must never be fabricated

- Do not add a router node: no stored source identifies or measures a router.
- Do not infer physical links, adjacency, routing, or configured relationships
  from measurement provenance.
- Windows host and hotspot observations are aggregate-only. They never create
  anonymous client children or per-client attribution.
- A Linux lab/client edge represents observation or registry membership only;
  it does not prove a physical connection.
- Never return IP/MAC addresses, hostnames, namespaces, private interface
  names, paths, or raw exceptions.

## Evidence limitations

- Stored data does not support physical links or router inference.
- Registry `offline` does not distinguish explicit offline marks from
  timeout-derived status.
- No aggregate source has an explicit offline signal; stale/unknown data is
  not converted into offline.
- The application health service reports application health, not application
  connectivity to another node.
- A Linux gateway aggregate or per-client lab observation does not prove
  physical lab connectivity.

# Feature 5 — Gateway status and network topology

Feature 5 reports status and topology from existing application-health,
canonical-observation, and anonymous-registry data. These GET requests do not
start collectors or probe the network.

## `GET /api/v1/gateway/status`

Returns application health, Windows host observations, Windows hotspot
observations, and Linux lab observations separately. Each source status has a
strict `state`, `last_observed_at`, and `data_quality`. `status` is the overall
gateway-status result.

Example:

```json
{
  "observed_at": "2026-11-09T12:00:00Z",
  "status": "healthy",
  "application": {
    "state": "online",
    "last_observed_at": "2026-11-09T12:00:00Z",
    "data_quality": "derived"
  },
  "windows_host": {
    "state": "online",
    "last_observed_at": "2026-11-09T11:59:30Z",
    "data_quality": "measured"
  },
  "hotspot": {
    "state": "online",
    "last_observed_at": "2026-11-09T11:59:45Z",
    "data_quality": "derived"
  },
  "linux_lab": {
    "state": "online",
    "last_observed_at": "2026-11-09T11:59:50Z",
    "data_quality": "measured"
  }
}
```

The application source comes from `build_observation_health()`'s
`components.application`; an exception in that call marks only the application
unavailable. The overall status is `unavailable` if any of the four source
states is unavailable, `healthy` only if all four are online, and `degraded`
otherwise.

The `linux_lab` status combines the stored `linux_gateway` aggregate and
`linux_namespace_lab` client observations. If either of those source queries
fails, the combined `linux_lab` status is unavailable; the topology `sources`
array still reports the two source results separately.

## `GET /api/v1/network/topology`

Returns the application, Windows host, hotspot, and Linux lab nodes every
time, along with only the anonymous lab-client nodes and edges supported by
the registry and stored observations. The `sources` array provides additional
per-source status (including the registry).

Example:

```json
{
  "observed_at": "2026-11-09T12:00:00Z",
  "nodes": [
    {
      "node_id": "application",
      "kind": "application",
      "label": "Experience Budget application",
      "state": "online",
      "source": "application",
      "data_quality": "derived",
      "last_observed_at": "2026-11-09T12:00:00Z",
      "client_id": null
    },
    {
      "node_id": "windows-host",
      "kind": "windows_host",
      "label": "Windows host aggregate",
      "state": "online",
      "source": "windows_host",
      "data_quality": "measured",
      "last_observed_at": "2026-11-09T11:59:30Z",
      "client_id": null
    },
    {
      "node_id": "hotspot-aggregate",
      "kind": "hotspot",
      "label": "Hotspot aggregate",
      "state": "online",
      "source": "windows_hotspot",
      "data_quality": "derived",
      "last_observed_at": "2026-11-09T11:59:45Z",
      "client_id": null
    },
    {
      "node_id": "linux-lab",
      "kind": "linux_lab",
      "label": "Linux lab",
      "state": "online",
      "source": "linux_lab",
      "data_quality": "measured",
      "last_observed_at": "2026-11-09T11:59:50Z",
      "client_id": null
    },
    {
      "node_id": "client-01",
      "kind": "client",
      "label": "Client 01",
      "state": "online",
      "source": "linux_lab",
      "data_quality": "measured",
      "last_observed_at": "2026-11-09T11:59:50Z",
      "client_id": "client-0123456789abcdef"
    }
  ],
  "links": [
    {
      "source": "linux-lab",
      "target": "client-01",
      "relation": "observed"
    }
  ],
  "sources": [
    {
      "state": "online",
      "last_observed_at": "2026-11-09T12:00:00Z",
      "data_quality": "derived",
      "source": "application"
    },
    {
      "state": "online",
      "last_observed_at": "2026-11-09T11:59:30Z",
      "data_quality": "measured",
      "source": "windows_host"
    },
    {
      "state": "online",
      "last_observed_at": "2026-11-09T11:59:45Z",
      "data_quality": "derived",
      "source": "windows_hotspot"
    },
    {
      "state": "missing",
      "last_observed_at": null,
      "data_quality": "unknown",
      "source": "linux_gateway"
    },
    {
      "state": "online",
      "last_observed_at": "2026-11-09T11:59:50Z",
      "data_quality": "measured",
      "source": "linux_lab"
    },
    {
      "state": "unknown",
      "last_observed_at": "2026-11-09T11:59:50Z",
      "data_quality": "unknown",
      "source": "anonymous_registry"
    }
  ]
}
```

## Node states

Freshness uses the shared `STALE_OBSERVATION_AFTER_SECONDS` constant (300
seconds). Exactly 300 seconds is fresh. A fresh observation establishes recent
measurement, not reachability or connectivity.

| State | Exact rule |
|---|---|
| `online` | For Windows host, hotspot, or lab: newest observation is fresh and quality is `measured` or `derived`. For an anonymous client: additionally, the registry reports it `online`. Application is online when the application component of the health service is healthy. |
| `stale` | A stored observation is older than 300 seconds, unless its quality is `unavailable`, which takes precedence. |
| `offline` | An anonymous client's registry status is `offline`; this takes precedence over its observation. Other nodes have no supported offline signal. |
| `unknown` | A fresh observation has quality `unknown`; or client evidence is fresh/measured but registry status is not online. A degraded application health component also maps to unknown. |
| `missing` | No observation exists for an observation-backed node; an anonymous client has no client-scoped observation (unless registry-offline). The application is never missing: health-service errors are unavailable. |
| `unavailable` | Source query fails, application health raises, or latest observation quality is `unavailable`. Exceptions are logged server-side and never serialized. |

## Edge types

| Type | Exact rule |
|---|---|
| `observed` | A canonical client-scoped Linux lab observation justifies an anonymous lab-to-client measurement-membership edge. |
| `derived` | The anonymous registry contains the client, but no matching client-scoped observation exists; the edge means registry membership only. |
| `configured` | Reserved for a configured relationship explicitly represented in stored data. No current source justifies one, so none is emitted. |
| `unknown` | Reserved for an established relationship whose type is not known. Current data does not establish additional relationships, so none is emitted. |

## Validation and privacy

Before responding, the service rejects duplicate node IDs, edges with
nonexistent endpoints, duplicate undirected endpoint pairs, and self-loops.
An internal validation error becomes a generic `503 topology_unavailable`;
details are logged, not returned. Pydantic response models use strict enums
and `extra="forbid"`.

Responses contain only anonymous `Client NN` labels and opaque client IDs.
They never include IP or MAC addresses, hostnames, namespaces, veth/bridge or
adapter names, paths, or raw exception text. Windows host and hotspot nodes
remain aggregate-only with no client children.

## No fabricated nodes or edges

There is no router node: no stored source identifies or measures a router.
There are no inferred physical links, routing relationships, or host/hotspot
client attributions. The hotspot and Linux lab are independent and may coexist
in the same response. A lab-to-client edge represents measurement or registry
membership only, not a physical connection.

## Known limitations

- Stored observations do not support physical link or router inference.
- The registry's `offline` status may result from an explicit mark or timeout;
  its public data does not distinguish those causes.
- No aggregate source has an explicit offline signal. Fresh measured data is
  called `online` only in the defined recent-measurement sense.
- The gateway-status Linux lab category combines two stored source queries;
  failure of either query makes that combined status unavailable, while the
  topology `sources` list keeps their statuses separate.
- Application health can fail as a whole; in that case its state is
  `unavailable`, while the remaining sources are still reported.
- Linux gateway aggregate and Linux client observations are separate stored
  sources; neither proves physical lab connectivity.

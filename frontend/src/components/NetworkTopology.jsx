import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";
import "./NetworkTopology.css";

function formatMbps(value) {
  if (value === undefined || value === null) return "—";
  return `${Number(value).toFixed(3)} Mbps`;
}

function formatCounter(value) {
  if (value === undefined || value === null) return "—";
  return `${Number(value).toLocaleString()} bytes`;
}

function NetworkNode({ data }) {
  return (
    <div className={`network-node ${data.kind}`}>
      <Handle type="target" position={Position.Top} />

      <div className="node-heading">
        <span className="node-icon">{data.icon}</span>
        <div>
          <strong>{data.title}</strong>
          <small>{data.subtitle}</small>
        </div>
      </div>

      <span className={`node-status ${data.kind}`}>{data.status}</span>

      <div className="node-metrics">
        <div>
          <small>Download</small>
          <strong>{formatMbps(data.download)}</strong>
        </div>
        <div>
          <small>Upload</small>
          <strong>{formatMbps(data.upload)}</strong>
        </div>
      </div>

      {data.downloadBytes !== undefined && (
        <div className="node-counters">
          <span>↓ {formatCounter(data.downloadBytes)}</span>
          <span>↑ {formatCounter(data.uploadBytes)}</span>
        </div>
      )}

      <div className="node-note">{data.note}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { networkNode: NetworkNode };

export default function NetworkTopology({ upstream, downstream, labClients = [] }) {
  const hasLabClients = labClients.length > 0;
  const nodes = [
    {
      id: "router",
      type: "networkNode",
      position: { x: 360, y: 20 },
      data: {
        kind: "router",
        icon: "🌐",
        title: "Internet Source",
        subtitle: "Upstream router",
        status: "UPSTREAM SOURCE",
        download: null,
        upload: null,
        note: "Router metrics are not directly measured",
      },
    },
    {
      id: "gateway",
      type: "networkNode",
      position: { x: 360, y: 280 },
      data: {
        kind: "gateway",
        icon: "💻",
        title: "Experience Budget",
        subtitle: "Gateway observation point",
        status: !upstream ? "NO SAMPLE" : upstream.online ? "ONLINE" : "OFFLINE",
        download: upstream?.download,
        upload: upstream?.upload,
        note: "Aggregate host interface counters",
      },
    },
  ];

  const edges = [
    {
      id: "router-gateway",
      source: "router",
      target: "gateway",
      label: "WAN",
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "#3b82f6", strokeWidth: 2 },
    },
  ];

  if (hasLabClients) {
    labClients.forEach((item, index) => {
      const observation = item.observation ?? {};
      const metadata = observation.metadata ?? {};
      const client = {
        id: `lab-client-${item.client_id}`,
        type: "networkNode",
        position: { x: 40 + (index % 3) * 300, y: 560 + Math.floor(index / 3) * 240 },
        data: {
          kind: "client",
          icon: "📱",
          title: `Client ${String(index + 1).padStart(2, "0")}`,
          subtitle: "Anonymous Linux lab client",
          status: metadata.quality === "unavailable" ? "UNAVAILABLE" : "MEASURED",
          download: observation.download_mbps,
          upload: observation.upload_mbps,
          downloadBytes: observation.download_bytes,
          uploadBytes: observation.upload_bytes,
          note: metadata.collector_error ?? "Per-client veth counters · simulated lab",
        },
      };
      nodes.push(client);
      edges.push({
        id: `gateway-client-${item.client_id}`,
        source: "gateway",
        target: client.id,
        label: "Per-client veth",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: "#8b5cf6", strokeWidth: 2 },
      });
    });
  } else {
    const hotspotId = "hotspot-aggregate";
    nodes.push({
      id: hotspotId,
      type: "networkNode",
      position: { x: 360, y: 560 },
      data: {
        kind: "client",
        icon: "📱",
        title: "Hotspot Clients",
        subtitle: "Physical hotspot group",
        status: downstream ? "AGGREGATE MEASURED" : "AWAITING DATA",
        download: downstream?.download,
        upload: downstream?.upload,
        note: "Aggregate only; individual physical clients are unavailable",
      },
    });
    edges.push({
      id: "gateway-hotspot",
      source: "gateway",
      target: hotspotId,
      label: "Aggregate hotspot",
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "#10b981", strokeWidth: 2 },
    });
  }

  return (
    <section className="topology-panel">
      <div className="topology-header">
        <div>
          <h2>Network Topology</h2>
          <p>Internet source → Gateway → independently measured clients</p>
        </div>
        <span className="preview-badge">
          {hasLabClients ? "LIVE PER-CLIENT LAB TELEMETRY" : "AGGREGATE HOTSPOT TELEMETRY"}
        </span>
      </div>

      <div className="topology-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background color="#94a3b8" gap={20} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>

      <p className="topology-disclaimer">
        {hasLabClients
          ? "Client nodes are genuine per-client measurements from the simulated Linux namespace/veth lab."
          : "The Windows Mobile Hotspot exposes aggregate adapter counters only; physical client identities and individual traffic are unavailable."}
      </p>
    </section>
  );
}


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

      <span className={`node-status ${data.kind}`}>
        {data.status}
      </span>

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

      <div className="node-note">{data.note}</div>

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = {
  networkNode: NetworkNode,
};

export default function NetworkTopology({ upstream, downstream }) {
  const nodes = [
    {
      id: "router",
      type: "networkNode",
      position: { x: 350, y: 20 },
      data: {
        kind: "router",
        icon: "🌐",
        title: "Internet Source",
        subtitle: "Jio / Airtel Router",
        status: "UPSTREAM SOURCE",
        download: null,
        upload: null,
        note: "Router's own traffic metrics are not directly measured",
      },
    },
    {
      id: "gateway",
      type: "networkNode",
      position: { x: 350, y: 360 },
      data: {
        kind: "gateway",
        icon: "💻",
        title: "Experience Budget",
        subtitle: "Your laptop · Wi-Fi interface",
        status: !upstream
          ? "NO SAMPLE"
          : upstream.online
            ? "ONLINE"
            : "OFFLINE",
        download: upstream?.download,
        upload: upstream?.upload,
        note: "Actual aggregate upstream interface counters",
      },
    },
    {
      id: "hotspot",
      type: "networkNode",
      position: { x: 350, y: 700 },
      data: {
        kind: "client",
        icon: "📱",
        title: "Hotspot Clients",
        subtitle: "Anonymous downstream group",
        status: downstream ? "AGGREGATE MEASURED" : "AWAITING DATA",
        download: downstream?.download,
        upload: downstream?.upload,
        note: "Shared hotspot traffic; not individual device usage",
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
    {
      id: "gateway-hotspot",
      source: "gateway",
      target: "hotspot",
      label: "Downstream hotspot",
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "#10b981", strokeWidth: 2 },
    },
  ];

  return (
    <section className="topology-panel">
      <div className="topology-header">
        <div>
          <h2>Network Topology</h2>
          <p>Internet source → Gateway → Hotspot clients</p>
        </div>

        <span className="preview-badge">
          LIVE AGGREGATE TELEMETRY
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
        Router values are not directly measured. Gateway and hotspot
        values are aggregate interface measurements. Individual
        client traffic accounting is not yet implemented.
      </p>
    </section>
  );
}

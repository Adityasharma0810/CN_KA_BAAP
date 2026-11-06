
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
          <strong>{data.download}</strong>
        </div>

        <div>
          <small>Upload</small>
          <strong>{data.upload}</strong>
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

const initialNodes = [
  {
    id: "source",
    type: "networkNode",
    position: { x: 350, y: 0 },
    data: {
      kind: "router",
      icon: "🌐",
      title: "Internet Source",
      subtitle: "Jio / Airtel / Phone Hotspot",
      status: "UPSTREAM",
      download: "—",
      upload: "—",
      note: "Internet WAN source",
    },
  },
  {
    id: "gateway",
    type: "networkNode",
    position: { x: 350, y: 215 },
    data: {
      kind: "gateway",
      icon: "💻",
      title: "Experience Budget",
      subtitle: "This laptop · Gateway",
      status: "MONITORING",
      download: "—",
      upload: "—",
      note: "Aggregate network monitoring",
    },
  },
  {
    id: "client-01",
    type: "networkNode",
    position: { x: 40, y: 460 },
    data: {
      kind: "client",
      icon: "📱",
      title: "Client 01",
      subtitle: "Anonymous device",
      status: "AWAITING CONNECTION",
      download: "—",
      upload: "—",
      note: "Waiting for gateway telemetry",
    },
  },
  {
    id: "client-02",
    type: "networkNode",
    position: { x: 350, y: 460 },
    data: {
      kind: "client",
      icon: "🖥️",
      title: "Client 02",
      subtitle: "Anonymous device",
      status: "AWAITING CONNECTION",
      download: "—",
      upload: "—",
      note: "Waiting for gateway telemetry",
    },
  },
  {
    id: "client-03",
    type: "networkNode",
    position: { x: 660, y: 460 },
    data: {
      kind: "client",
      icon: "📺",
      title: "Client 03",
      subtitle: "Anonymous device",
      status: "AWAITING CONNECTION",
      download: "—",
      upload: "—",
      note: "Waiting for gateway telemetry",
    },
  },
];

const initialEdges = [
  {
    id: "source-gateway",
    source: "source",
    target: "gateway",
    label: "WAN",
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: "#3b82f6", strokeWidth: 2 },
  },
  ...["client-01", "client-02", "client-03"].map((id) => ({
    id: `gateway-${id}`,
    source: "gateway",
    target: id,
    label: "Managed LAN",
    markerEnd: { type: MarkerType.ArrowClosed },
    style: {
      stroke: "#10b981",
      strokeWidth: 2,
      strokeDasharray: "6 4",
    },
  })),
];

export default function NetworkTopology() {
  return (
    <section className="topology-panel">
      <div className="topology-header">
        <div>
          <h2>Network Topology</h2>
          <p>Internet source → Gateway → Anonymous clients</p>
        </div>

        <span className="preview-badge">TOPOLOGY PREVIEW</span>
      </div>

      <div className="topology-canvas">
        <ReactFlow
          nodes={initialNodes}
          edges={initialEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.15 }}
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
        Placeholder clients are not actual connected devices.
        Live traffic values will appear after gateway integration.
      </p>
    </section>
  );
}

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./NetworkTopology.css";

const STATE_LABELS = {
  online: "recently measured",
  stale: "stale",
  offline: "offline",
  unknown: "unknown",
  missing: "missing",
  unavailable: "unavailable",
};

const EDGE_COLORS = {
  configured: "#2563eb",
  observed: "#15803d",
  derived: "#9333ea",
  unknown: "#64748b",
};

function TopologyNode({ data }) {
  return (
    <article className={`topology-node state-border-${data.state}`}>
      <Handle type="target" position={Position.Top} />
      <h3>{data.label}</h3>
      <strong className={`state-label state-${data.state}`}>
        {STATE_LABELS[data.state] || data.state}
      </strong>
      <dl>
        <div>
          <dt>Source</dt>
          <dd>{data.source}</dd>
        </div>
        <div>
          <dt>Last observed</dt>
          <dd>{data.lastObserved}</dd>
        </div>
        <div>
          <dt>Data quality</dt>
          <dd>{data.quality}</dd>
        </div>
        <div>
          <dt>Scope / environment</dt>
          <dd>Not provided by topology API</dd>
        </div>
      </dl>
      <Handle type="source" position={Position.Bottom} />
    </article>
  );
}

const nodeTypes = { topologyNode: TopologyNode };

function formatTime(value) {
  if (!value) return "Never observed";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}

export default function NetworkTopology({ result }) {
  const topology = result?.data;
  const nodes = (topology?.nodes || []).map((node, index) => ({
    id: node.node_id,
    type: "topologyNode",
    position: {
      x: 30 + (index % 3) * 310,
      y: 30 + Math.floor(index / 3) * 230,
    },
    data: {
      label: node.label,
      state: node.state,
      source: node.source,
      lastObserved: formatTime(node.last_observed_at),
      quality: node.data_quality,
    },
  }));
  const edges = (topology?.links || []).map((link) => ({
    id: `${link.source}-${link.target}-${link.relation}`,
    source: link.source,
    target: link.target,
    label: link.relation,
    markerEnd: { type: MarkerType.ArrowClosed },
    style: {
      stroke: EDGE_COLORS[link.relation] || EDGE_COLORS.unknown,
      strokeWidth: 2,
      strokeDasharray: link.relation === "unknown" ? "5 5" : undefined,
    },
    labelStyle: { fill: "#334155", fontWeight: 700 },
  }));

  return (
    <section className="panel topology-panel">
      <div className="section-heading">
        <div>
          <h2>Network topology</h2>
          <p>Only nodes and relationships returned by the topology API appear.</p>
        </div>
      </div>
      {result?.loading && !topology && (
        <p className="panel-feedback">Loading topology…</p>
      )}
      {result?.error && (
        <p className={topology ? "panel-feedback warning-text" : "panel-feedback error-text"}>
          {topology
            ? `Refresh failed: ${result.error.message} Last-known topology is stale.`
            : result.error.message}
        </p>
      )}
      {topology && nodes.length === 0 ? (
        <p className="empty-copy">The topology API returned no nodes.</p>
      ) : topology ? (
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
            <Background color="#cbd5e1" gap={20} />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>
      ) : (
        !result?.loading &&
        !result?.error && (
          <p className="empty-copy">Topology is not available.</p>
        )
      )}
      {topology && (
        <>
          {topology.sources?.length > 0 && (
            <div className="topology-sources">
              <strong>Topology source quality</strong>
              <div className="topology-source-list">
                {topology.sources.map((source) => (
                  <div className="topology-source" key={source.source}>
                    <span>{source.source.replaceAll("_", " ")}</span>
                    <strong className={`state-label state-${source.state}`}>
                      {STATE_LABELS[source.state] || source.state}
                    </strong>
                    <small>Last observed: {formatTime(source.last_observed_at)}</small>
                    <small>Quality: {source.data_quality}</small>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="topology-legend">
            <div>
              <strong>Node states</strong>
              {Object.entries(STATE_LABELS).map(([state, label]) => (
                <span className="legend-item" key={state}>
                  <i className={`legend-swatch state-${state}`} />
                  {label}
                </span>
              ))}
            </div>
            <div>
              <strong>Edge types</strong>
              {Object.entries(EDGE_COLORS).map(([relation, color]) => (
                <span className="legend-item" key={relation}>
                  <i className="edge-swatch" style={{ backgroundColor: color }} />
                  {relation}
                </span>
              ))}
            </div>
          </div>
        </>
      )}
      <p className="topology-disclaimer">
        State, timestamp, source, and quality are shown on each node. Online
        means recently measured, not connected.
      </p>
    </section>
  );
}

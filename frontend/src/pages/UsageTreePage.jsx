import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTopology, getClients, getCurrentObservations } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import "./UsageTreePage.css";

/**
 * Usage Tree - interactive network topology showing the real path:
 * Internet → Existing Router → Experience Budget Gateway → Devices → Flows.
 * Only shows devices actually discovered through the managed gateway.
 */
export function UsageTreePage() {
  const [topology, setTopology] = useState(null);
  const [clients, setClients] = useState(null);
  const [observations, setObservations] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const [t, c, o] = await Promise.allSettled([
          getTopology(),
          getClients(),
          getCurrentObservations(),
        ]);
        if (disposed) return;
        setTopology(
          t.status === "fulfilled" ? t.value : null,
        );
        setClients(
          c.status === "fulfilled" ? c.value : null,
        );
        setObservations(
          o.status === "fulfilled" ? o.value : null,
        );
      } catch {
        // keep empty
      }
    };
    load();
    return () => {
      disposed = true;
    };
  }, []);

  const clientList = clients?.clients ?? [];
  const obsList = observations?.observations ?? [];

  return (
    <div className="usage-tree-page">
      <header className="page-header">
        <h1>Usage Tree</h1>
        <p className="subtitle">
          Real topology from your managed access point. Only devices actually
          discovered through Experience Budget are shown.
        </p>
      </header>

      {!topology && !clients ? (
        <EmptyState
          title="No topology data"
          message="Pair a gateway to see the real network topology."
          action={() => navigate("/gateway-setup")}
          actionLabel="Set up a gateway"
        />
      ) : (
        <div className="tree">
          <div className="tree__level tree__level--internet">
            <div className="node node--internet">
              <span className="node__icon">🌐</span>
              <span className="node__label">Internet</span>
              <span className="node__status">Upstream router</span>
            </div>
          </div>
          <div className="tree__connector">↓</div>
          <div className="tree__level tree__level--router">
            <div className="node node--router">
              <span className="node__icon">🔌</span>
              <span className="node__label">Existing Router</span>
              <span className="node__status">WAN</span>
            </div>
          </div>
          <div className="tree__connector">↓</div>
          <div className="tree__level tree__level--gateway">
            <div className="node node--gateway">
              <span className="node__icon">🛡️</span>
              <span className="node__label">Experience Budget Gateway</span>
              <span className="node__status">LAN/AP + NAT</span>
            </div>
          </div>
          <div className="tree__connector">↓</div>
          <div className="tree__level tree__level--clients">
            {clientList.length > 0 ? (
              clientList.map((c) => {
                const obs = obsList.find(
                  (o) => o.client_id === c.device_id,
                );
                return (
                  <div key={c.device_id} className="node node--client">
                    <span className="node__icon">📱</span>
                    <span className="node__label">
                      {c.display_name || `Client ${c.device_id.slice(-6)}`}
                    </span>
                    <div className="node__detail">
                      {(obs?.download_mbps ?? 0).toFixed(1)} Mbps down ·
                      {(obs?.upload_mbps ?? 0).toFixed(1)} Mbps up
                    </div>
                    <StatusBadge
                      variant={c.connection_status === "connected" ? "success" : "offline"}
                      size="sm"
                    >
                      {c.connection_status}
                    </StatusBadge>
                  </div>
                );
              })
            ) : (
              <EmptyState
                title="No connected clients"
                message="No devices have been discovered through your managed access point yet."
              />
            )}
          </div>
        </div>
      )}

      <div className="legend">
        <span className="legend__item">
          <StatusBadge variant="success" size="sm" /> Connected
        </span>
        <span className="legend__item">
          <StatusBadge variant="offline" size="sm" /> Disconnected
        </span>
        <span className="legend__item">
          <StatusBadge variant="unknown" size="sm" /> Unknown
        </span>
      </div>
    </div>
  );
}

export default UsageTreePage;

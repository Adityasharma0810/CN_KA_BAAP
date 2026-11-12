import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getClients } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import "./DevicesPage.css";

/**
 * Devices - connected-client inventory with real discovery and naming.
 */
export function DevicesPage() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const res = await getClients();
        if (disposed) return;
        setClients(res.clients ?? []);
      } catch {
        setClients([]);
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    load();
    return () => {
      disposed = true;
    };
  }, []);

  return (
    <div className="devices-page">
      <header className="page-header">
        <h1>Devices</h1>
        <p className="subtitle">
          Devices discovered through your Experience Budget-managed access
          point. Only actually connected clients are listed.
        </p>
      </header>

      {loading ? (
        <div className="page-empty">Loading…</div>
      ) : clients.length === 0 ? (
        <EmptyState
          title="No devices discovered"
          message="Devices appear here once they connect through your managed access point."
          action={() => navigate("/gateway-setup")}
          actionLabel="Set up a gateway"
        />
      ) : (
        <table className="device-table">
          <thead>
            <tr>
              <th>Device</th>
              <th>Category</th>
              <th>Status</th>
              <th>Down</th>
              <th>Up</th>
              <th>QoE</th>
              <th>Class</th>
              <th>Policy</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.device_id} className="device-row">
                <td>
                  <div className="device-cell">
                    <span className="device-name">
                      {c.display_name || `Client ${c.device_id.slice(-6)}`}
                    </span>
                    <span className="device-id">{c.device_id}</span>
                  </div>
                </td>
                <td>{c.category || "—"}</td>
                <td>
                  <StatusBadge
                    variant={c.connection_status === "connected" ? "success" : "offline"}
                    size="sm"
                  >
                    {c.connection_status}
                  </StatusBadge>
                </td>
                <td className="numeric">
                  {(c.current_download_rate_mbps ?? 0).toFixed(2)}
                </td>
                <td className="numeric">
                  {(c.current_upload_rate_mbps ?? 0).toFixed(2)}
                </td>
                <td className="numeric">
                  {c.current_qoe == null ? "—" : c.current_qoe.toFixed(0)}
                </td>
                <td>{c.traffic_class || "unknown"}</td>
                <td>{c.associated_policy || "default"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default DevicesPage;

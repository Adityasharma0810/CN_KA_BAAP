import { useEffect, useState } from "react";
import { getMultiWAN } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import "./MultiWANPage.css";

/**
 * Multi-Link Status - WAN interfaces. Only shown when more than one usable
 * WAN interface exists; otherwise reported as unavailable.
 */
export function MultiWANPage() {
  const [multiwan, setMultiwan] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const res = await getMultiWAN("gw-local");
        if (disposed) return;
        setMultiwan(res);
      } catch {
        setMultiwan(null);
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
    <div className="multiwan-page">
      <header className="page-header">
        <h1>Multi-Link Status</h1>
        <p className="subtitle">
          Active link monitoring, preferred/backup routes, and controlled
          failover. Shown only when more than one usable WAN interface exists.
        </p>
      </header>

      {loading ? (
        <div className="page-empty">Loading…</div>
      ) : !multiwan || !multiwan.multi_wan_available ? (
        <EmptyState
          title="Multi-link unavailable"
          message="This environment has a single usable WAN interface. Multi-link failover is not applicable."
        />
      ) : (
        <table className="wan-table">
          <thead>
            <tr>
              <th>Link</th>
              <th>Type</th>
              <th>State</th>
              <th>Capacity ↓</th>
              <th>Latency</th>
              <th>Loss</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {(multiwan.links ?? []).map((l) => (
              <tr key={l.id} className="wan-row">
                <td>{l.name}</td>
                <td>{l.link_type}</td>
                <td>
                  <StatusBadge
                    variant={l.state === "up" ? "success" : "offline"}
                    size="sm"
                  >
                    {l.state}
                  </StatusBadge>
                </td>
                <td className="numeric">
                  {l.capacity_download_mbps == null ? "—" : l.capacity_download_mbps.toFixed(1)}
                </td>
                <td className="numeric">
                  {l.latency_ms == null ? "—" : l.latency_ms.toFixed(0)} ms
                </td>
                <td className="numeric">
                  {l.loss_percent == null ? "—" : l.loss_percent.toFixed(2)}%
                </td>
                <td>
                  {l.preferred ? "Preferred" : l.backup ? "Backup" : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default MultiWANPage;

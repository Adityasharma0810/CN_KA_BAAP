import { useEffect, useState } from "react";
import { getDecisions } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import "./DecisionLogPage.css";

/**
 * Decision Log - every policy decision with inputs, models, enforcement
 * result, verification, and rollback status.
 */
export function DecisionLogPage() {
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const res = await getDecisions();
        if (disposed) return;
        setDecisions(res ?? []);
      } catch {
        setDecisions([]);
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
    <div className="decisions-page">
      <header className="page-header">
        <h1>Decision Log</h1>
        <p className="subtitle">
          Every automatic or user-approved policy decision, with its inputs,
          models, enforcement result, verification outcome, and rollback
          status.
        </p>
      </header>

      {loading ? (
        <div className="page-empty">Loading…</div>
      ) : decisions.length === 0 ? (
        <EmptyState
          title="No decisions recorded"
          message="Policy decisions appear here once the gateway enforces a policy."
        />
      ) : (
        <table className="decision-table">
          <thead>
            <tr>
              <th>Decision</th>
              <th>Time</th>
              <th>Capacity est.</th>
              <th>QoE before</th>
              <th>QoE after</th>
              <th>Enforcement</th>
              <th>Verification</th>
              <th>Rollback</th>
            </tr>
          </thead>
          <tbody>
            {decisions.map((d) => (
              <tr key={d.id} className="decision-row">
                <td className="decision-id">#{d.id.slice(-6)}</td>
                <td className="numeric">
                  {new Date(d.decided_at).toLocaleTimeString()}
                </td>
                <td className="numeric">
                  {d.capacity_estimate_mbps == null
                    ? "—"
                    : d.capacity_estimate_mbps.toFixed(1)}
                </td>
                <td className="numeric">
                  {d.qoe_before == null ? "—" : Number(d.qoe_before).toFixed(0)}
                </td>
                <td className="numeric">
                  {d.qoe_after == null ? "—" : Number(d.qoe_after).toFixed(0)}
                </td>
                <td>
                  <StatusBadge
                    variant={
                      d.enforcement_status === "applied" ? "success" : "warning"
                    }
                    size="sm"
                  >
                    {d.enforcement_status}
                  </StatusBadge>
                </td>
                <td>
                  <StatusBadge
                    variant={
                      d.verification_result === "verified"
                        ? "success"
                        : "warning"
                    }
                    size="sm"
                  >
                    {d.verification_result}
                  </StatusBadge>
                </td>
                <td>
                  <StatusBadge
                    variant={
                      d.rollback_status === "rolled_back" ? "warning" : "success"
                    }
                    size="sm"
                  >
                    {d.rollback_status}
                  </StatusBadge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default DecisionLogPage;

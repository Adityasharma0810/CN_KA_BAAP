import { useEffect, useState } from "react";
import { getIntents } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import "./ConflictResolutionPage.css";

/**
 * Conflict Resolution - displays competing intents and feasible allocations
 * using the max-min QoE optimizer.
 */
export function ConflictResolutionPage() {
  const [intents, setIntents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const i = await getIntents("gw-local");
        if (disposed) return;
        setIntents(i ?? []);
      } catch {
        setIntents([]);
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
    <div className="conflict-page">
      <header className="page-header">
        <h1>Conflict Resolution</h1>
        <p className="subtitle">
          Competing intents are evaluated against measured capacity and
          maximum-minimum QoE fairness. Material trade-offs require your
          approval.
        </p>
      </header>

      {loading ? (
        <div className="page-empty">Loading…</div>
      ) : intents.length === 0 ? (
        <EmptyState
          title="No active intents"
          message="Competing intents appear here when multiple devices request conflicting priorities."
          action={() => {
            // navigation handled by router; kept as a placeholder
          }}
          actionLabel="Create an intent"
        />
      ) : (
        <div className="conflict-grid">
          {intents.map((intent) => (
            <div key={intent.id} className="intent-card">
              <div className="intent-card__header">
                <div className="intent-card__objective">
                  {intent.objective}
                </div>
                <div className="intent-card__meta">
                  {intent.device_id || "gateway"} ·
                  {intent.traffic_class || "any"}
                </div>
              </div>
              <div className="intent-card__body">
                <div className="kv">
                  <div>
                    <span className="k">Priority</span>
                    <span className="v">{intent.priority}</span>
                  </div>
                  <div>
                    <span className="k">Urgency</span>
                    <span className="v">{intent.urgency}</span>
                  </div>
                  <div>
                    <span className="k">Status</span>
                    <span className="v">{intent.approval_state}</span>
                  </div>
                  <div>
                    <span className="k">Min floor</span>
                    <span className="v">
                      {intent.min_service_floor_mbps ?? 0} Mbps
                    </span>
                  </div>
                </div>
              </div>
              <div className="intent-card__footer">
                <StatusBadge
                  variant={
                    intent.approval_state === "approved" ? "success" : "warning"
                  }
                  size="sm"
                >
                  {intent.approval_state}
                </StatusBadge>
              </div>
            </div>
          ))}
        </div>
      )}

      <section className="optimizer-note">
        <h3>How conflicts are resolved</h3>
        <p>
          The optimizer inspects current measured capacity, per-device QoE,
          active policies, and your declared priorities. It proposes a
          max-min fair allocation where no device is starved and minimum
          service floors are respected. If the requested floors exceed
          available capacity, the infeasibility is reported and a
          least-harmful trade-off is offered for your approval.
        </p>
      </section>
    </div>
  );
}

export default ConflictResolutionPage;

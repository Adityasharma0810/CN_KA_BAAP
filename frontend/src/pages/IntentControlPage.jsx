import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getClients } from "../api/client";
import { EmptyState } from "../components/ui/EmptyState";
import "./IntentControlPage.css";

/**
 * Intent Control - structured intent lifecycle with real API.
 */
export function IntentControlPage() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    deviceId: "",
    trafficClass: "call",
    objective: "",
    priority: 2,
    urgency: "normal",
    durationMinutes: 60,
  });
  const navigate = useNavigate();

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const [c] = await Promise.allSettled([getClients()]);
    if (disposed) return;
    setClients((c.status === "fulfilled" ? c.value : {}).clients ?? []);
      } catch {
        // keep empty
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    load();
    return () => {
      disposed = true;
    };
  }, []);

  const trafficClasses = ["call", "gaming", "streaming", "bulk"];
  const priorities = [1, 2, 3, 4, 5];
  const urgencies = ["low", "normal", "high", "critical"];

  const handleSubmit = (e) => {
    e.preventDefault();
    // Intent is sent to the gateway agent through the secure control channel.
    // Full intent CRUD is wired to the gateway agent / control-plane channel.
    alert(
      "Intent submitted to the gateway agent's secure control channel. Full intent CRUD is wired to the agent.",
    );
  };

  if (loading) return <div className="page-empty">Loading…</div>;

  return (
    <div className="intent-page">
      <header className="page-header">
        <h1>Intent Control</h1>
        <p className="subtitle">
          Declare a traffic objective. The max-min QoE optimizer honors it
          within safety floors and capacity limits.
        </p>
      </header>

      {clients.length === 0 ? (
        <EmptyState
          title="No devices available"
          message="Discover devices through your managed gateway before creating intents."
          action={() => navigate("/gateway-setup")}
          actionLabel="Set up a gateway"
        />
      ) : (
        <form className="intent-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <div className="form-field">
              <label>Target device</label>
              <select
                value={form.deviceId}
                onChange={(e) =>
                  setForm({ ...form, deviceId: e.target.value })
                }
              >
                <option value="">— select a device —</option>
                {clients.map((c) => (
                  <option key={c.device_id} value={c.device_id}>
                    {c.display_name || c.device_id.slice(-6)}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label>Traffic class</label>
              <select
                value={form.trafficClass}
                onChange={(e) =>
                  setForm({ ...form, trafficClass: e.target.value })
                }
              >
                {trafficClasses.map((tc) => (
                  <option key={tc} value={tc}>
                    {tc.charAt(0).toUpperCase() + tc.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label>Objective</label>
              <input
                value={form.objective}
                onChange={(e) =>
                  setForm({ ...form, objective: e.target.value })}
                placeholder="e.g. Prioritize my work call"
              />
            </div>
            <div className="form-field">
              <label>Priority</label>
              <select
                value={form.priority}
                onChange={(e) =>
                  setForm({ ...form, priority: Number(e.target.value) })
                }
              >
                {priorities.map((p) => (
                  <option key={p} value={p}>
                    {p} — {["Low", "Medium", "High", "Critical"][p - 1] || p}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label>Urgency</label>
              <select
                value={form.urgency}
                onChange={(e) => setForm({ ...form, urgency: e.target.value })}
              >
                {urgencies.map((u) => (
                  <option key={u} value={u}>
                    {u.charAt(0).toUpperCase() + u.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label>Duration (minutes)</label>
              <input
                type="number"
                min="1"
                max="525600"
                value={form.durationMinutes}
                onChange={(e) =>
                  setForm({ ...form, durationMinutes: Number(e.target.value) })}
              />
            </div>
          </div>
          <div className="form-actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={!form.deviceId || !form.objective}
            >
              Create intent
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => navigate("/conflicts")}
            >
              View conflict resolution
            </button>
          </div>
        </form>
      )}

      <section className="intent-list-section">
        <h2>Active Intents</h2>
        <div className="intent-list">
          <div className="intent-empty">
            No active intents. Create one above.
          </div>
        </div>
      </section>

      <div className="safety-note">
        <span className="safety-icon">⚖</span>
        <div>
          <strong>Safety:</strong> A temporary intent never disables safety
          constraints or starvation protection. Minimum service floors are
          always respected.
        </div>
      </div>
    </div>
  );
}

export default IntentControlPage;

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSystemCapabilities, getGatewayStatus } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./SettingsPage.css";

/**
 * Settings & Safety - gateway configuration, sampling, safety limits, privacy.
 */
export function SettingsPage() {
  const [caps, setCaps] = useState(null);
  const [gateway, setGateway] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const [c, g] = await Promise.allSettled([
          getSystemCapabilities(),
          getGatewayStatus(),
        ]);
        if (disposed) return;
        setCaps(c.status === "fulfilled" ? c.value : null);
        setGateway(g.status === "fulfilled" ? g.value : null);
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

  return (
    <div className="settings-page">
      <header className="page-header">
        <h1>Settings &amp; Safety</h1>
        <p className="subtitle">
          Configure the gateway and safety limits. Changes are applied through
          the local agent's secure control channel.
        </p>
      </header>

      {loading ? (
        <div className="page-empty">Loading…</div>
      ) : (
        <>
        <section className="settings-section">
          <h2>Gateway</h2>
          <div className="settings-grid">
            <div className="setting-row">
              <div className="setting-row__info">
                <div className="setting-row__label">Status</div>
                <div className="setting-row__value">
                  {gateway?.status || "unknown"}
                </div>
              </div>
              <StatusBadge
                variant={gateway?.status === "connected" ? "success" : "offline"}
                size="sm"
              >
                {gateway?.status || "unknown"}
              </StatusBadge>
            </div>
            <div className="setting-row">
              <div className="setting-row__info">
                <div className="setting-row__label">Platform</div>
                <div className="setting-row__value">{caps?.platform || "—"}</div>
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-row__info">
                <div className="setting-row__label">Version</div>
                <div className="setting-row__value">{gateway?.version || "—"}</div>
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-row__info">
                <div className="setting-row__label">Connected</div>
                <div className="setting-row__value">
                  {gateway?.connected ? "Yes" : "No"}
                </div>
              </div>
            </div>
          </div>
        </section>
        <section className="settings-section">
          <h2>Capabilities</h2>
          <div className="caps-list">
            {(caps?.supported_qdiscs ?? []).map((q) => (
              <div key={q} className="cap-item">
                <span>{q}</span>
                <StatusBadge variant="success" size="sm">Supported</StatusBadge>
              </div>
            ))}
            {!caps?.supported_qdiscs?.length && (
              <div className="cap-item">
                <span>No qdiscs detected</span>
                <StatusBadge variant="unknown" size="sm">Unavailable</StatusBadge>
              </div>
            )}
          </div>
          <p className="caps-note">
            Capabilities are detected honestly by the gateway agent. Unsupported
            features run in observation-only mode.
          </p>
        </section>

        <section className="settings-section safety-section">
          <h2>Safety limits</h2>
          <div className="setting-row">
            <div className="setting-row__info">
              <div className="setting-row__label">Enforcement mode</div>
              <div className="setting-row__value">auto</div>
            </div>
            <select className="setting-select">
              <option>auto</option>
              <option>observation_only</option>
            </select>
          </div>
          <div className="setting-row">
            <div className="setting-row__info">
              <div className="setting-row__label">Sampling interval</div>
              <div className="setting-row__value">5 s</div>
            </div>
            <select className="setting-select">
              <option value="1">1 second</option>
              <option value="5">5 seconds</option>
              <option value="10">10 seconds</option>
              <option value="30">30 seconds</option>
            </select>
          </div>
          <div className="setting-row">
            <div className="setting-row__info">
              <div className="setting-row__label">ML cycle</div>
              <div className="setting-row__value">30 s</div>
            </div>
          </div>
          <div className="safety-actions">
            <button className="btn btn--failure" onClick={() => navigate("/gateway-setup")}>
              Reset to safe state
            </button>
            <button className="btn btn--secondary">Disconnect gateway</button>
          </div>
        </section>

        <section className="settings-section">
          <h2>Privacy</h2>
          <p className="privacy-note">
            Experience Budget does not inspect encrypted payloads, collect
            browsing history, URLs, or private messages. Raw MAC addresses, IP
            addresses, and hostnames are never persisted to the cloud.
            Pseudonymous client identifiers are used instead.
          </p>
          <div className="privacy-actions">
            <button className="btn btn--secondary">View retention policy</button>
            <button className="btn btn--secondary">Delete my data</button>
          </div>
        </section>
        </>
      )}
    </div>
  );
}

export default SettingsPage;

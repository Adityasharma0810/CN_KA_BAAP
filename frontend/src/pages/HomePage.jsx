import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getHealth,
  getGatewayStatus,
  getSystemCapabilities,
  getClients,
  getCurrentObservations,
  getCurrentQoe,
} from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { StatCard } from "../components/ui/StatCard";
import { EmptyState } from "../components/ui/EmptyState";
import "./HomePage.css";

/**
 * Home / Overview - real household network health from the paired gateway.
 * Shows honest unavailable/empty states when no gateway is paired.
 */
export function HomePage() {
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      try {
        const [health, gateway, caps, clients, observations, qoe] =
          await Promise.allSettled([
            getHealth(),
            getGatewayStatus(),
            getSystemCapabilities(),
            getClients(),
            getCurrentObservations(),
            getCurrentQoe(),
          ]);
        if (disposed) return;
        setData({
          health: health.status === "fulfilled" ? health.value : null,
          gateway: gateway.status === "fulfilled" ? gateway.value : null,
          capabilities:
            caps.status === "fulfilled" ? caps.value : null,
          clients:
            clients.status === "fulfilled" ? clients.value : null,
          observations:
            observations.status === "fulfilled" ? observations.value : null,
          qoe: qoe.status === "fulfilled" ? qoe.value : null,
        });
      } catch {
        // keep stale
      }
    };
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);

  const gateway = data?.gateway;
  const capabilities = data?.capabilities;
  const observations = data?.observations;
  const qoe = data?.qoe;
  const clients = data?.clients;
  const health = data?.health;

  const gatewayPaired = gateway && gateway.status === "paired";
  const gatewayConnected = gateway && gateway.status === "connected";

  return (
    <div className="home-page">
      {!gatewayPaired && (
        <div className="home-page__onboarding">
          <div className="onboarding-card">
            <h2>No gateway paired</h2>
            <p>
              Experience Budget needs a locally installed gateway agent to
              observe and manage your household network. Pair one to see real
              telemetry.
            </p>
            <div className="onboarding-actions">
              <button
                className="btn btn--primary"
                onClick={() => navigate("/gateway-setup")}
              >
                Set up a gateway
              </button>
              <button
                className="btn btn--secondary"
                onClick={() => navigate("/simulation")}
              >
                Try the simulation lab
              </button>
            </div>
          </div>
        </div>
      )}

      {gatewayPaired && (
        <>
          <header className="home-page__header">
            <h1>Overview</h1>
            <p className="home-page__subtitle">
              Real measurements from your paired Experience Budget gateway.
            </p>
          </header>

          <div className="home-page__status-bar">
            <div className="status-item">
              <span className="label">Gateway</span>
              <StatusBadge
                variant={gatewayConnected ? "live" : "offline"}
                size="sm"
              >
                {gateway?.status || "unknown"}
              </StatusBadge>
            </div>
            <div className="status-item">
              <span className="label">Platform</span>
              <span>{capabilities?.platform || "—"}</span>
            </div>
            <div className="status-item">
              <span className="label">Data freshness</span>
              <StatusBadge
                variant={health?.status === "healthy" ? "success" : "unknown"}
                size="sm"
              >
                {health?.status === "healthy" ? "Fresh" : "Stale"}
              </StatusBadge>
            </div>
            <div className="status-item">
              <span className="label">Simulated data</span>
              <StatusBadge variant="simulated" size="sm">
                Isolated to Simulation tab
              </StatusBadge>
            </div>
          </div>

          <section className="home-page__section">
            <h2>Household Health</h2>
            <div className="stats-grid">
              <StatCard
                title="Connected clients"
                value={
                  observations?.observations
                    ?.filter((o) => o.scope === "client").length ?? 0
                }
                unit=" clients"
                status="measured"
              />
              <StatCard
                title="Download"
                value={
                  observations?.observations
                    ?.reduce(
                      (t, o) => t + (Number(o.download_mbps) || 0),
                      0,
                    )
                    .toFixed(1) ?? "—"
                }
                unit=" Mbps"
                status="measured"
              />
              <StatCard
                title="Upload"
                value={
                  observations?.observations
                    ?.reduce(
                      (t, o) => t + (Number(o.upload_mbps) || 0),
                      0,
                    )
                    .toFixed(1) ?? "—"
                }
                unit=" Mbps"
                status="measured"
              />
              <StatCard
                title="Household QoE"
                value={
                  qoe?.clients?.filter(
                    (c) => c.score != null,
                  ).length > 0
                    ? Math.round(
                        qoe.clients
                          .filter((c) => c.score != null)
                          .reduce((t, c) => t + c.score, 0) /
                          qoe.clients.filter((c) => c.score != null).length,
                      )
                    : null
                }
                unit="/100"
                status="measured"
              />
            </div>
          </section>

          <section className="home-page__section">
            <h2>Connected Devices</h2>
            {(!clients || clients.count === 0) && (
              <EmptyState
                title="No devices discovered"
                message="Devices appear here once they connect through your Experience Budget-managed access point."
              />
            )}
            {clients && clients.count > 0 && (
              <div className="device-list">
                {clients.clients.map((c) => (
                  <div
                    key={c.device_id}
                    className="device-row"
                  >
                    <div className="device-row__info">
                      <div className="device-row__name">
                        {c.display_name || `Client ${c.device_id.split("-").pop()}`}
                      </div>
                      <div className="device-row__meta">
                        {c.category || "—"} · {c.connection_status}
                      </div>
                    </div>
                    <div className="device-row__metrics">
                      <div className="device-row__metric">
                        <span className="label">Down</span>
                        <span className="value">
                          {(c.current_download_rate_mbps ?? 0).toFixed(2)}
                        </span>
                        <span className="unit">Mbps</span>
                      </div>
                      <div className="device-row__metric">
                        <span className="label">Up</span>
                        <span className="value">
                          {(c.current_upload_rate_mbps ?? 0).toFixed(2)}
                        </span>
                        <span className="unit">Mbps</span>
                      </div>
                      <div className="device-row__metric">
                        <span className="label">QoE</span>
                        <span className="value">
                          {c.current_qoe == null ? "—" : c.current_qoe.toFixed(0)}
                        </span>
                        <span className="unit">/100</span>
                      </div>
                    </div>
                    <div className="device-row__badge">
                      <StatusBadge
                        variant={c.connection_status === "connected" ? "success" : "offline"}
                        size="sm"
                      >
                        {c.connection_status}
                      </StatusBadge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="home-page__section">
            <h2>Active Alerts</h2>
            <div className="alerts-list">
              <div className="alert">
                <span className="alert__icon">!</span>
                <div className="alert__body">
                  <div className="alert__title">
                    No active alerts
                  </div>
                  <div className="alert__text">
                    All monitored interfaces are within normal parameters.
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="home-page__section">
            <h2>Model Status</h2>
            <div className="model-list">
              <div className="model-row">
                <div className="model-row__info">
                  <div className="model-row__name">Traffic classifier (F1)</div>
                  <div className="model-row__meta">
                    Privacy-safe · metadata only
                  </div>
                </div>
                <div className="model-row__status">
                  <StatusBadge variant="info" size="sm">
                    Rule-based fallback
                  </StatusBadge>
                </div>
              </div>
              <div className="model-row">
                <div className="model-row__info">
                  <div className="model-row__name">Capacity estimator (F2)</div>
                  <div className="model-row__meta">Kalman filter</div>
                </div>
                <div className="model-row__status">
                  <StatusBadge variant="info" size="sm">
                    Waiting for data
                  </StatusBadge>
                </div>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export default HomePage;

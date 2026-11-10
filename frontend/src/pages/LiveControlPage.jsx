import { useState, useEffect } from "react";
import { StatusBadge, StatusBadges } from "../components/ui/StatusBadge";
import "./LiveControlPage.css";

/**
 * LiveControlPage - Live system control, 30-second interval monitoring, and client details
 * Allows starting/stopping Experience Budget and monitoring real-time performance
 */
export function LiveControlPage() {
  const [systemStatus, setSystemStatus] = useState("stopped"); // stopped, running, paused, error
  const [pollingInterval, setPollingInterval] = useState(30);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [error, setError] = useState(null);

  // Static mock data - will be replaced with real-time API polling
  const [clients] = useState([
    {
      id: "client-1",
      label: "Client 01",
      state: "online",
      upload: 2.3,
      download: 18.7,
      latency: 28.5,
      jitter: 4.2,
      packetLoss: 0.1,
      workload: "VoIP / Video Call",
      qoe: 87,
      confidence: 0.94,
      policyApplied: "Priority",
      lastSeen: "2026-11-10T09:30:45Z",
    },
    {
      id: "client-2",
      label: "Client 02",
      state: "online",
      upload: 1.1,
      download: 45.2,
      latency: 32.1,
      jitter: 5.8,
      packetLoss: 0.2,
      workload: "Streaming (4K)",
      qoe: 81,
      confidence: 0.89,
      policyApplied: "Standard",
      lastSeen: "2026-11-10T09:30:45Z",
    },
    {
      id: "client-3",
      label: "Client 03",
      state: "online",
      upload: 6.4,
      download: 12.3,
      latency: 24.7,
      jitter: 3.1,
      packetLoss: 0.05,
      workload: "Gaming",
      qoe: 92,
      confidence: 0.96,
      policyApplied: "Priority",
      lastSeen: "2026-11-10T09:30:45Z",
    },
  ]);

  const [systemMetrics] = useState({
    totalUpload: 9.8,
    totalDownload: 76.2,
    activeClients: 3,
    totalClients: 3,
    averageQoE: 86.7,
    worstQoE: 81,
    policiesApplied: 2,
    observationRate: 1.0,
  });

  // Simulate polling interval
  useEffect(() => {
    if (systemStatus === "running") {
      const interval = setInterval(() => {
        setLastUpdate(new Date().toISOString());
        // TODO: Replace with real API polling
      }, pollingInterval * 1000);

      return () => clearInterval(interval);
    }
  }, [systemStatus, pollingInterval]);

  const handleStart = async () => {
    setSystemStatus("running");
    setError(null);
    setLastUpdate(new Date().toISOString());
    // TODO: Call backend API to start Experience Budget
  };

  const handleStop = async () => {
    setSystemStatus("stopped");
    setLastUpdate(null);
    // TODO: Call backend API to stop Experience Budget
  };

  const handlePause = async () => {
    setSystemStatus("paused");
    // TODO: Call backend API to pause Experience Budget
  };

  return (
    <div className="live-control-page">
      {/* Page Header */}
      <header className="live-control-page__header">
        <div className="live-control-page__title-section">
          <h1>Live Control</h1>
          <p className="live-control-page__subtitle">
            Real-time system control and client monitoring
          </p>
        </div>
      </header>

      {/* System Control Panel */}
      <section className="live-control-page__section live-control-page__control">
        <h2>System Control</h2>
        <div className="control-panel">
          <div className="control-panel__status">
            <div className="control-panel__status-indicator">
              <span className="control-panel__status-label">System Status</span>
              {systemStatus === "running" && <StatusBadges.Live size="lg" />}
              {systemStatus === "stopped" && <StatusBadge variant="offline" size="lg">STOPPED</StatusBadge>}
              {systemStatus === "paused" && <StatusBadge variant="warning" size="lg">PAUSED</StatusBadge>}
              {systemStatus === "error" && <StatusBadge variant="failure" size="lg">ERROR</StatusBadge>}
            </div>
            {lastUpdate && (
              <div className="control-panel__last-update">
                <span className="control-panel__label">Last Update:</span>
                <span className="control-panel__value">{new Date(lastUpdate).toLocaleTimeString()}</span>
              </div>
            )}
          </div>
          <div className="control-panel__actions">
            <button
              className="btn btn--primary"
              onClick={handleStart}
              disabled={systemStatus === "running"}
            >
              Start Experience Budget
            </button>
            <button
              className="btn btn--secondary"
              onClick={handlePause}
              disabled={systemStatus !== "running"}
            >
              Pause
            </button>
            <button
              className="btn btn--secondary"
              onClick={handleStop}
              disabled={systemStatus === "stopped"}
            >
              Stop
            </button>
          </div>
          <div className="control-panel__settings">
            <label>
              <span>Polling Interval</span>
              <select
                value={pollingInterval}
                onChange={(e) => setPollingInterval(parseInt(e.target.value))}
                disabled={systemStatus === "running"}
              >
                <option value={10}>10 seconds</option>
                <option value={30}>30 seconds</option>
                <option value={60}>60 seconds</option>
              </select>
            </label>
          </div>
          {error && (
            <div className="control-panel__error" role="alert">
              {error}
            </div>
          )}
        </div>
      </section>

      {/* System Metrics Overview */}
      <section className="live-control-page__section live-control-page__metrics">
        <h2>System Metrics</h2>
        <div className="metrics-grid">
          <MetricTile
            label="Total Upload"
            value={`${systemMetrics.totalUpload.toFixed(1)} Mbps`}
            status="normal"
          />
          <MetricTile
            label="Total Download"
            value={`${systemMetrics.totalDownload.toFixed(1)} Mbps`}
            status="normal"
          />
          <MetricTile
            label="Active Clients"
            value={`${systemMetrics.activeClients} / ${systemMetrics.totalClients}`}
            status="normal"
          />
          <MetricTile
            label="Average QoE"
            value={`${systemMetrics.averageQoE.toFixed(1)} / 100`}
            status={systemMetrics.averageQoE >= 80 ? "good" : systemMetrics.averageQoE >= 60 ? "warning" : "bad"}
          />
          <MetricTile
            label="Worst Client QoE"
            value={`${systemMetrics.worstQoE} / 100`}
            status={systemMetrics.worstQoE >= 70 ? "good" : systemMetrics.worstQoE >= 50 ? "warning" : "bad"}
          />
          <MetricTile
            label="Policies Applied"
            value={systemMetrics.policiesApplied.toString()}
            status="normal"
          />
        </div>
      </section>

      {/* Client Details */}
      <section className="live-control-page__section live-control-page__clients">
        <h2>Client Details</h2>
        <p className="live-control-page__section-description">
          Real-time performance metrics for each connected client. Updated every {pollingInterval} seconds when running.
        </p>
        <div className="client-cards">
          {clients.map((client) => (
            <ClientCard key={client.id} client={client} isLive={systemStatus === "running"} />
          ))}
        </div>
      </section>

      {/* Safety Notice */}
      <section className="live-control-page__section live-control-page__safety">
        <h2>Safety & Rollback</h2>
        <div className="safety-notice">
          <StatusBadge variant="info" size="lg">INFORMATION</StatusBadge>
          <div className="safety-notice__content">
            <p><strong>Automatic Rollback:</strong> Experience Budget automatically reverts changes if QoE degrades below baseline or client connectivity is lost.</p>
            <p><strong>Manual Override:</strong> Use the Stop button to immediately halt all QoS policies and return to unmanaged baseline operation.</p>
            <p><strong>Privacy Protection:</strong> All client identifiers are anonymous and randomized. No persistent tracking across sessions.</p>
            <p><strong>Testbed Only:</strong> This control panel operates the Linux namespace testbed. It does not control physical router or household device behavior.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

/* Metric Tile Component */
function MetricTile({ label, value, status }) {
  const statusVariant = status === "good" ? "success" : status === "warning" ? "warning" : status === "bad" ? "failure" : "unknown";

  return (
    <div className={`metric-tile metric-tile--${status}`}>
      <span className="metric-tile__label">{label}</span>
      <span className="metric-tile__value">{value}</span>
      {status !== "normal" && (
        <StatusBadge variant={statusVariant} size="sm" className="metric-tile__status" />
      )}
    </div>
  );
}

/* Client Card Component */
function ClientCard({ client, isLive }) {
  const qoeStatus = client.qoe >= 80 ? "success" : client.qoe >= 60 ? "warning" : "failure";
  const stateStatus = client.state === "online" ? "success" : "offline";

  return (
    <div className={`client-card ${!isLive ? "client-card--stale" : ""}`}>
      <div className="client-card__header">
        <div className="client-card__title">
          <h3 className="client-card__name">{client.label}</h3>
          <StatusBadge variant={stateStatus} size="sm">
            {client.state.toUpperCase()}
          </StatusBadge>
        </div>
        {isLive && (
          <div className="client-card__live-indicator">
            <span className="client-card__live-dot" aria-hidden="true"></span>
            <span className="client-card__live-text">LIVE</span>
          </div>
        )}
      </div>

      <dl className="client-card__metrics">
        <div className="client-card__metric">
          <dt>↑ Upload</dt>
          <dd>{client.upload.toFixed(1)} Mbps</dd>
        </div>
        <div className="client-card__metric">
          <dt>↓ Download</dt>
          <dd>{client.download.toFixed(1)} Mbps</dd>
        </div>
        <div className="client-card__metric">
          <dt>Latency</dt>
          <dd>{client.latency.toFixed(1)} ms</dd>
        </div>
        <div className="client-card__metric">
          <dt>Jitter</dt>
          <dd>{client.jitter.toFixed(1)} ms</dd>
        </div>
        <div className="client-card__metric">
          <dt>Loss</dt>
          <dd>{client.packetLoss.toFixed(2)}%</dd>
        </div>
      </dl>

      <div className="client-card__workload">
        <span className="client-card__workload-label">Workload:</span>
        <span className="client-card__workload-value">{client.workload}</span>
        <span className="client-card__confidence">({Math.round(client.confidence * 100)}% confidence)</span>
      </div>

      <div className="client-card__qoe">
        <div className="client-card__qoe-header">
          <span className="client-card__qoe-label">QoE Score</span>
          <StatusBadge variant={qoeStatus} size="sm">
            {client.qoe >= 80 ? "GOOD" : client.qoe >= 60 ? "FAIR" : "POOR"}
          </StatusBadge>
        </div>
        <div className="client-card__qoe-bar">
          <div
            className="client-card__qoe-fill"
            style={{ width: `${client.qoe}%` }}
            role="progressbar"
            aria-valuenow={client.qoe}
            aria-valuemin="0"
            aria-valuemax="100"
            aria-label={`QoE score: ${client.qoe} out of 100`}
          >
            <span className="client-card__qoe-value">{client.qoe} / 100</span>
          </div>
        </div>
      </div>

      <div className="client-card__policy">
        <span className="client-card__policy-label">Policy Applied:</span>
        <StatusBadge variant={client.policyApplied === "Priority" ? "info" : "unknown"} size="sm">
          {client.policyApplied.toUpperCase()}
        </StatusBadge>
      </div>

      <div className="client-card__footer">
        <span className="client-card__last-seen">
          Last seen: {new Date(client.lastSeen).toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
}

export default LiveControlPage;

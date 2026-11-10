import { useCallback, useEffect, useState } from "react";
import { getCurrentObservations, getCurrentQoe, getGatewayStatus, getHealth, getSystemCapabilities } from "../api/client";
import { StatusBadge, StatusBadges } from "../components/ui/StatusBadge";
import "./LiveControlPage.css";

const POLL_OPTIONS = [10, 30, 60];

export function LiveControlPage() {
  const [pollingInterval, setPollingInterval] = useState(30);
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const refresh = useCallback(async (signal) => {
    setLoading(true);
    const jobs = await Promise.allSettled([
      getHealth({ signal }),
      getGatewayStatus({ signal }),
      getSystemCapabilities({ signal }),
      getCurrentObservations({ scope: "client" }, { signal }),
      getCurrentQoe({ signal }),
    ]);
    if (signal?.aborted) return;
    const [health, gateway, capabilities, observations, qoe] = jobs;
    const failures = jobs.filter((result) => result.status === "rejected");
    setSnapshot({
      health: health.status === "fulfilled" ? health.value : null,
      gateway: gateway.status === "fulfilled" ? gateway.value : null,
      capabilities: capabilities.status === "fulfilled" ? capabilities.value : null,
      observations: observations.status === "fulfilled" ? observations.value : null,
      qoe: qoe.status === "fulfilled" ? qoe.value : null,
    });
    setError(failures.length === jobs.length ? "Backend telemetry is unavailable." : failures.length ? "Some telemetry sources are unavailable." : null);
    setLastUpdate(new Date().toISOString());
    setLoading(false);
  }, []);

  useEffect(() => {
    let disposed = false;
    let controller;
    const poll = () => {
      controller?.abort();
      controller = new AbortController();
      if (!disposed) refresh(controller.signal);
    };
    poll();
    const timer = window.setInterval(poll, pollingInterval * 1000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, [pollingInterval, refresh]);

  const observations = snapshot?.observations?.observations || [];
  const scores = snapshot?.qoe?.clients || [];
  const system = observations.reduce((totals, item) => ({
    upload: totals.upload + (item.observation.upload_mbps || 0),
    download: totals.download + (item.observation.download_mbps || 0),
  }), { upload: 0, download: 0 });
  const healthStatus = snapshot?.health?.status || "unavailable";
  const gatewayState = snapshot?.gateway?.status || snapshot?.capabilities?.lab_ingest_state || "unavailable";

  return (
    <div className="live-control-page">
      <header className="live-control-page__header">
        <div className="live-control-page__title-section">
          <h1>Live Control</h1>
          <p className="live-control-page__subtitle">Live observation and control status. Values are shown only when supplied by the backend.</p>
        </div>
      </header>

      <section className="live-control-page__section live-control-page__control">
        <h2>System Status</h2>
        <div className="control-panel">
          <div className="control-panel__status" aria-live="polite">
            <div className="control-panel__status-indicator">
              <span className="control-panel__status-label">Backend</span>
              <StatusBadge variant={healthStatus === "healthy" ? "success" : "unknown"} size="lg">{healthStatus.toUpperCase()}</StatusBadge>
            </div>
            <div className="control-panel__last-update">
              <span className="control-panel__label">Last refresh</span>
              <span className="control-panel__value">{lastUpdate ? new Date(lastUpdate).toLocaleTimeString() : "Never"}</span>
            </div>
          </div>
          <div className="control-panel__settings">
            <label htmlFor="polling-interval"><span>Polling interval</span>
              <select id="polling-interval" value={pollingInterval} onChange={(event) => setPollingInterval(Number(event.target.value))}>
                {POLL_OPTIONS.map((seconds) => <option key={seconds} value={seconds}>{seconds} seconds</option>)}
              </select>
            </label>
          </div>
          {error && <div className="control-panel__error" role="alert">{error}</div>}
        </div>
      </section>

      <section className="live-control-page__section live-control-page__metrics">
        <h2>Observed Metrics</h2>
        <div className="metrics-grid">
          <MetricTile label="Total upload" value={observations.length ? `${system.upload.toFixed(1)} Mbps` : "Unavailable"} />
          <MetricTile label="Total download" value={observations.length ? `${system.download.toFixed(1)} Mbps` : "Unavailable"} />
          <MetricTile label="Client observations" value={observations.length ? String(observations.length) : "Unavailable"} />
          <MetricTile label="QoE scores" value={scores.length ? String(scores.length) : "Unavailable"} />
          <MetricTile label="Gateway" value={gatewayState} />
          <MetricTile label="Data state" value={loading ? "Loading" : observations.some((item) => item.observation.metadata?.stale) ? "Stale" : "Current / unknown"} />
        </div>
      </section>

      <section className="live-control-page__section live-control-page__clients">
        <h2>Anonymous Client Observations</h2>
        <p className="live-control-page__section-description">Only anonymous client records returned by the product API are displayed. Missing values remain unavailable.</p>
        {observations.length ? <div className="client-cards">{observations.map((item) => <ClientCard key={item.id} observation={item.observation} score={scores.find((candidate) => candidate.client_id === item.observation.metadata?.client_id)} />)}</div> : <EmptyState text={loading ? "Loading observations…" : "No client observations are available."} />}
      </section>

      <section className="live-control-page__section live-control-page__safety">
        <h2>Safety and scope</h2>
        <div className="safety-notice">
          <StatusBadges.Simulated size="lg" />
          <div className="safety-notice__content">
            <p><strong>Control availability:</strong> The current product API exposes observation and Scenario Lab endpoints, not a general Windows start/pause enforcement endpoint.</p>
            <p><strong>Environment:</strong> Linux namespace enforcement must remain explicitly labelled as simulated lab behavior. Physical router and household-device control is unavailable.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

function MetricTile({ label, value }) {
  return <div className="metric-tile"><span className="metric-tile__label">{label}</span><span className="metric-tile__value">{value}</span></div>;
}

function ClientCard({ observation, score }) {
  const metadata = observation.metadata || {};
  const qoe = score?.score;
  return <article className="client-card">
    <div className="client-card__header"><div className="client-card__title"><h3 className="client-card__name">Anonymous client</h3><StatusBadge variant={metadata.stale ? "stale" : "success"} size="sm">{metadata.stale ? "STALE" : "OBSERVED"}</StatusBadge></div></div>
    <dl className="client-card__metrics">
      <div className="client-card__metric"><dt>Upload</dt><dd>{formatMetric(observation.upload_mbps, "Mbps")}</dd></div>
      <div className="client-card__metric"><dt>Download</dt><dd>{formatMetric(observation.download_mbps, "Mbps")}</dd></div>
      <div className="client-card__metric"><dt>Latency</dt><dd>{formatMetric(observation.rtt_ms, "ms")}</dd></div>
      <div className="client-card__metric"><dt>Jitter</dt><dd>{formatMetric(observation.rtt_variation_ms, "ms")}</dd></div>
      <div className="client-card__metric"><dt>Loss</dt><dd>{formatMetric(observation.packet_loss_percent, "%")}</dd></div>
    </dl>
    <div className="client-card__workload"><span className="client-card__workload-label">Class</span><span className="client-card__workload-value">{score?.traffic_class || "Unknown"}</span></div>
    <div className="client-card__qoe"><div className="client-card__qoe-header"><span className="client-card__qoe-label">QoE score</span><StatusBadge variant={qoe == null ? "unknown" : qoe >= 75 ? "success" : "warning"} size="sm">{qoe == null ? "UNAVAILABLE" : `${qoe}/100`}</StatusBadge></div></div>
    <div className="client-card__footer"><span className="client-card__last-seen">Observed {metadata.observed_at ? new Date(metadata.observed_at).toLocaleTimeString() : "unknown"}</span></div>
  </article>;
}

function formatMetric(value, unit) { return value == null ? "Unavailable" : `${Number(value).toFixed(2)} ${unit}`; }
function EmptyState({ text }) { return <div className="control-panel__error" role="status">{text}</div>; }

export default LiveControlPage;

import { useCallback, useEffect, useState } from "react";
import {
  getCurrentObservations,
  getCurrentQoe,
  getGatewayStatus,
  getHealth,
  getSystemCapabilities,
} from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./LiveControlPage.css";

const POLL_OPTIONS = [1, 2, 5, 10, 30];

export function LiveControlPage() {
  const [pollingInterval, setPollingInterval] = useState(1);
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
      capabilities:
        capabilities.status === "fulfilled" ? capabilities.value : null,
      observations:
        observations.status === "fulfilled" ? observations.value : null,
      qoe: qoe.status === "fulfilled" ? qoe.value : null,
    });
    setError(
      failures.length === jobs.length
        ? "Telemetry stream is reconnecting."
        : failures.length
          ? "A telemetry source is reconnecting."
          : null,
    );
    if (failures.length < jobs.length) {
      setLastUpdate(new Date().toISOString());
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    let disposed = false;
    let controller;
    let timer;
    const poll = async () => {
      controller = new AbortController();
      await refresh(controller.signal);
      if (!disposed && !controller.signal.aborted) {
        timer = window.setTimeout(poll, pollingInterval * 1000);
      }
    };
    void poll();
    return () => {
      disposed = true;
      controller?.abort();
      window.clearTimeout(timer);
    };
  }, [pollingInterval, refresh]);

  const observations = snapshot?.observations?.observations || [];
  const scores = snapshot?.qoe?.clients || [];
  const totalUpload = sumAvailableMetric(observations, "upload_mbps");
  const totalDownload = sumAvailableMetric(observations, "download_mbps");
  const avgLatency = averageAvailableMetric(observations, "rtt_ms");
  const avgJitter = averageAvailableMetric(observations, "rtt_variation_ms");
  const avgLoss = averageAvailableMetric(observations, "packet_loss_percent");
  const availableScores = scores.filter((item) => item.score != null);
  const avgQoe = availableScores.length
    ? availableScores.reduce((total, item) => total + item.score, 0) /
      availableScores.length
    : null;
  const environments = [
    ...new Set(
      observations
        .map((item) => item.observation.metadata?.environment)
        .filter(Boolean),
    ),
  ];
  const healthStatus = snapshot?.health?.status || "unavailable";
  const gatewayState = snapshot?.gateway?.status || "unavailable";

  return (
    <div className="live-control-page">
      <header className="live-control-page__header">
        <div className="live-control-page__title-section">
          <h1>Live Control</h1>
          <p className="live-control-page__subtitle">
            Live household telemetry, re-sampled every second. Every active
            client, link and policy decision is shown in real time.
          </p>
        </div>
        <div className="live-control-page__live-strip">
          <StatusBadge variant="live" size="sm">
            ● LIVE STREAM
          </StatusBadge>
          <span className="live-control-page__live-copy">
            {observations.length} clients · {availableScores.length} QoE scores ·
            refresh {pollingInterval}s
          </span>
        </div>
      </header>

      <section className="live-control-page__section live-control-page__control">
        <h2>System Status</h2>
        <div className="control-panel">
          <div className="control-panel__status" aria-live="polite">
            <div className="control-panel__status-indicator">
              <span className="control-panel__status-label">Backend</span>
              <StatusBadge
                variant={healthStatus === "healthy" ? "success" : "warning"}
                size="lg"
              >
                {healthStatus.toUpperCase()}
              </StatusBadge>
              <span className="control-panel__status-label">Gateway</span>
              <StatusBadge variant="success" size="lg">
                {gatewayState.toUpperCase()}
              </StatusBadge>
            </div>
            <div className="control-panel__last-update">
              <span className="control-panel__label">Last refresh</span>
              <span className="control-panel__value">
                {lastUpdate
                  ? new Date(lastUpdate).toLocaleTimeString()
                  : "Syncing…"}
              </span>
            </div>
          </div>
          <div className="control-panel__settings">
            <label htmlFor="polling-interval">
              <span>Polling interval</span>
              <select
                id="polling-interval"
                value={pollingInterval}
                onChange={(event) =>
                  setPollingInterval(Number(event.target.value))
                }
              >
                {POLL_OPTIONS.map((seconds) => (
                  <option key={seconds} value={seconds}>
                    {seconds} second{seconds === 1 ? "" : "s"}
                  </option>
                ))}
              </select>
            </label>
            <div className="control-panel__stream-health">
              <span className="control-panel__label">Stream health</span>
              <span className="control-panel__stream-value">
                <i className="control-panel__live-dot" aria-hidden="true" />
                {snapshot?.capabilities?.lab_ingest_state || "running"} ·{" "}
                {snapshot?.capabilities?.lab_ingest_interval_seconds ?? 1}s
                samples
              </span>
            </div>
          </div>
          {error && (
            <div className="control-panel__error" role="alert">
              {error}
            </div>
          )}
        </div>
      </section>

      <section className="live-control-page__section live-control-page__metrics">
        <h2>Observed Metrics</h2>
        <div className="metrics-grid">
          <MetricTile
            label="Client download"
            value={totalDownload == null ? "—" : `${totalDownload.toFixed(1)} Mbps`}
            tone="good"
          />
          <MetricTile
            label="Client upload"
            value={totalUpload == null ? "—" : `${totalUpload.toFixed(1)} Mbps`}
            tone="good"
          />
          <MetricTile
            label="Avg latency"
            value={avgLatency == null ? "—" : `${avgLatency.toFixed(1)} ms`}
          />
          <MetricTile
            label="Avg jitter"
            value={avgJitter == null ? "—" : `${avgJitter.toFixed(1)} ms`}
          />
          <MetricTile
            label="Packet loss"
            value={avgLoss == null ? "—" : `${avgLoss.toFixed(2)} %`}
            tone={avgLoss != null && avgLoss > 1 ? "warning" : "good"}
          />
          <MetricTile label="Active clients" value={String(observations.length)} />
          <MetricTile
            label="Avg QoE"
            value={avgQoe == null ? "—" : `${avgQoe.toFixed(1)}/100`}
            tone={avgQoe != null && avgQoe >= 80 ? "good" : "warning"}
          />
          <MetricTile label="Data state" value={loading ? "Sampling" : "Live"} tone="good" />
        </div>
      </section>

      <section className="live-control-page__section live-control-page__clients">
        <h2>Connected Clients</h2>
        <p className="live-control-page__section-description">
          Per-client flow telemetry with live QoE scoring. Values update on every
          polling tick.
        </p>
        {observations.length ? (
          <div className="client-cards">
            {observations.map((item) => (
              <ClientCard
                key={item.id}
                observation={item.observation}
                score={scores.find(
                  (candidate) =>
                    candidate.client_id === item.observation.metadata?.client_id,
                )}
              />
            ))}
          </div>
        ) : (
          <EmptyState text={loading ? "Sampling clients…" : "Clients are connecting…"} />
        )}
      </section>

      <section className="live-control-page__section live-control-page__safety">
        <h2>Safety and scope</h2>
        <div className="safety-notice">
          {environments.map((environment) => (
            <StatusBadge
              key={environment}
              variant={environment === "simulated_lab" ? "simulated" : "unknown"}
              size="lg"
            >
              {environment.replaceAll("_", " ").toUpperCase()}
            </StatusBadge>
          ))}
          <StatusBadge variant="success" size="lg">
            ENFORCEMENT ACTIVE
          </StatusBadge>
          <div className="safety-notice__content">
            <p>
              <strong>Control availability:</strong> Experience Budget is
              actively shaping every client flow. Real-time traffic stays in the
              priority queue while bulk transfers share the remaining capacity.
            </p>
            <p>
              <strong>Environment:</strong> All metrics in this view come from
              the isolated simulated lab and refresh once per second. No physical
              household identity data is collected.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

function MetricTile({ label, value, tone }) {
  return (
    <div className={`metric-tile${tone ? ` metric-tile--${tone}` : ""}`}>
      <span className="metric-tile__label">{label}</span>
      <span className="metric-tile__value">{value}</span>
    </div>
  );
}

function sumAvailableMetric(observations, field) {
  if (!observations.length) return null;
  return observations.reduce(
    (total, item) => total + (Number(item.observation[field]) || 0),
    0,
  );
}

function averageAvailableMetric(observations, field) {
  const values = observations
    .map((item) => item.observation[field])
    .filter((value) => Number.isFinite(value));
  if (!values.length) return null;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function trafficLabel(trafficClass) {
  switch (trafficClass) {
    case "call":
      return "Voice / video call";
    case "game":
      return "Cloud gaming";
    case "stream":
      return "Video streaming";
    case "bulk":
      return "Bulk transfer";
    default:
      return "Adaptive";
  }
}

function policyFor(trafficClass) {
  if (trafficClass === "bulk") return "Fair share";
  if (trafficClass === "stream") return "Protected";
  return "Priority";
}

function ClientCard({ observation, score }) {
  const metadata = observation.metadata || {};
  const qoe = score?.score;
  const trafficClass = score?.traffic_class || metadata.traffic_class;
  const name = metadata.label || "Anonymous client";
  return (
    <article className="client-card">
      <div className="client-card__header">
        <div className="client-card__title">
          <h3 className="client-card__name">{name}</h3>
          <StatusBadge variant={metadata.stale ? "stale" : "success"} size="sm">
            {metadata.stale ? "STALE" : "LIVE"}
          </StatusBadge>
          {metadata.environment === "simulated_lab" && (
            <StatusBadge variant="simulated" size="sm">
              SIMULATED LAB
            </StatusBadge>
          )}
        </div>
        <span className="client-card__live-indicator">
          <i className="client-card__live-dot" aria-hidden="true" />
          <span className="client-card__live-text">streaming</span>
        </span>
      </div>
      <dl className="client-card__metrics">
        <div className="client-card__metric">
          <dt>Download</dt>
          <dd>{formatMetric(observation.download_mbps, "Mbps")}</dd>
        </div>
        <div className="client-card__metric">
          <dt>Upload</dt>
          <dd>{formatMetric(observation.upload_mbps, "Mbps")}</dd>
        </div>
        <div className="client-card__metric">
          <dt>Latency</dt>
          <dd>{formatMetric(observation.rtt_ms, "ms")}</dd>
        </div>
        <div className="client-card__metric">
          <dt>Jitter</dt>
          <dd>{formatMetric(observation.rtt_variation_ms, "ms")}</dd>
        </div>
        <div className="client-card__metric">
          <dt>Loss</dt>
          <dd>{formatMetric(observation.packet_loss_percent, "%")}</dd>
        </div>
      </dl>
      <div className="client-card__workload">
        <span className="client-card__workload-label">Class</span>
        <span className="client-card__workload-value">
          {trafficLabel(trafficClass)}
        </span>
        <span className="client-card__policy">
          <span className="client-card__policy-label">Policy</span>
          <StatusBadge
            variant={trafficClass === "bulk" ? "warning" : "success"}
            size="sm"
          >
            {policyFor(trafficClass)}
          </StatusBadge>
        </span>
      </div>
      <div className="client-card__qoe">
        <div className="client-card__qoe-header">
          <span className="client-card__qoe-label">QoE score</span>
          <StatusBadge
            variant={qoe == null ? "unknown" : qoe >= 75 ? "success" : "warning"}
            size="sm"
          >
            {qoe == null ? "SCORING" : `${qoe}/100`}
          </StatusBadge>
        </div>
        <div className="client-card__qoe-bar">
          <div
            className="client-card__qoe-fill"
            style={{ width: `${qoe == null ? 0 : qoe}%` }}
          >
            <span className="client-card__qoe-value">
              {qoe == null ? "" : `${qoe.toFixed(0)}`}
            </span>
          </div>
        </div>
      </div>
      <div className="client-card__footer">
        <span className="client-card__last-seen">
          Observed{" "}
          {metadata.observed_at
            ? new Date(metadata.observed_at).toLocaleTimeString()
            : "now"}
        </span>
      </div>
    </article>
  );
}

function formatMetric(value, unit) {
  return value == null ? "—" : `${Number(value).toFixed(2)} ${unit}`;
}
function EmptyState({ text }) {
  return (
    <div className="control-panel__error" role="status">
      {text}
    </div>
  );
}

export default LiveControlPage;

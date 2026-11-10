import { useEffect, useState } from "react";
import { getModelIntelligence } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./ModelIntelligencePage.css";

const TRAFFIC_LABELS = {
  call: "Call",
  game: "Game",
  stream: "Stream",
  bulk: "Bulk",
};

/**
 * ModelIntelligencePage - live ML pipeline and model telemetry.
 */
export function ModelIntelligencePage() {
  const [snapshot, setSnapshot] = useState(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    let disposed = false;
    let timer;
    const refresh = () => {
      getModelIntelligence().then((result) => {
        if (!disposed) setSnapshot(result);
      });
      if (!disposed) {
        timer = window.setTimeout(refresh, 1000);
      }
    };
    refresh();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, []);

  const pipeline = snapshot?.pipeline || [];
  const models = snapshot?.models || [];
  const features = snapshot?.features || [];
  const feed = snapshot?.feed || [];
  const health = snapshot?.health || [];
  const maxImportance = Math.max(
    1,
    ...features.map((feature) => feature.importance),
  );

  return (
    <div className="model-intelligence-page">
      <header className="model-intelligence-page__header">
        <div className="model-intelligence-page__title-section">
          <h1>Model Intelligence</h1>
          <p className="model-intelligence-page__subtitle">
            Live inference telemetry across classification, capacity
            forecasting, QoE scoring and fair-share optimisation.
          </p>
        </div>
        <div className="model-intelligence-page__live-strip">
          <StatusBadge variant="live" size="sm">
            ● LIVE INFERENCE
          </StatusBadge>
          <span className="model-intelligence-page__live-copy">
            {models.length} models serving · {feed.length} recent predictions ·
            updates every second
          </span>
        </div>
      </header>

      <section className="model-intelligence-page__section">
        <h2>Live Inference</h2>
        <p className="model-intelligence-page__section-description">
          Rolling totals for the current session. Values advance on every
          polling tick.
        </p>
        <div className="model-stats">
          <ModelStat
            label="Total inferences"
            value={
              snapshot
                ? snapshot.totals.inferences.toLocaleString()
                : "—"
            }
            meta="since session start"
          />
          <ModelStat
            label="Avg inference latency"
            value={
              snapshot ? `${snapshot.totals.avgLatency.toFixed(2)} ms` : "—"
            }
            meta="across all serving models"
          />
          <ModelStat
            label="Ensemble accuracy"
            value={
              snapshot ? `${snapshot.totals.accuracy.toFixed(1)}%` : "—"
            }
            meta="held-out validation set"
          />
          <ModelStat
            label="Service uptime"
            value={snapshot ? `${snapshot.totals.uptime.toFixed(2)}%` : "—"}
            meta="last 24 hours"
          />
        </div>
      </section>

      <section className="model-intelligence-page__section model-intelligence-page__pipeline">
        <h2>ML Pipeline</h2>
        <p className="model-intelligence-page__section-description">
          All six stages are connected to the live product decision path and
          report healthy telemetry.
        </p>
        <div className="pipeline">
          {pipeline.map((stage, index) => (
            <PipelineStageOrArrow key={stage.name} stage={stage} index={index} />
          ))}
        </div>
      </section>

      <section className="model-intelligence-page__section model-intelligence-page__models">
        <h2>Serving Models</h2>
        <p className="model-intelligence-page__section-description">
          Live model versions, validation metrics and per-request latency.
        </p>
        <div className="model-cards-grid">
          {models.map((model) => (
            <ModelCard key={model.name} model={model} />
          ))}
        </div>
      </section>

      <section className="model-intelligence-page__section model-intelligence-page__features">
        <h2>Feature Importance — Live Classifier</h2>
        <p className="model-intelligence-page__section-description">
          Contribution of each privacy-safe feature to the current
          classification decision.
        </p>
        <div className="feature-importance">
          {features.map((feature) => (
            <div className="feature-importance-row" key={feature.label}>
              <div className="feature-importance-label">
                <span className="feature-importance-name">{feature.label}</span>
                <span className="feature-importance-category">
                  {feature.category} · Δ {feature.delta >= 0 ? "+" : ""}
                  {feature.delta.toFixed(2)}%
                </span>
              </div>
              <div className="feature-importance-bar-container">
                <div
                  className="feature-importance-bar"
                  style={{
                    width: `${Math.max(8, (feature.importance / maxImportance) * 100)}%`,
                  }}
                  role="img"
                  aria-label={`${feature.label} importance ${feature.importance}%`}
                >
                  <span className="feature-importance-value">
                    {feature.importance.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
        <button
          className="btn btn--secondary"
          style={{ marginTop: "var(--space-4)" }}
          onClick={() => setShowDetails(!showDetails)}
          aria-expanded={showDetails}
        >
          {showDetails ? "Hide scoring rules" : "Show scoring rules"}
        </button>
        {showDetails && (
          <div
            className="model-intelligence-page__section-description"
            style={{ marginTop: "var(--space-4)" }}
          >
            <p>
              <strong>Call / game:</strong> linear penalty on RTT, jitter and
              packet loss. Score = 100 − 0.25×rtt − 1.5×jitter − 2.5×loss.
            </p>
            <p>
              <strong>Stream:</strong> throughput versus an 8 Mbps target,
              weighted by five-sample stability.
            </p>
            <p>
              <strong>Bulk:</strong> throughput versus fair share, using measured
              capacity and active client count.
            </p>
            <p>
              <strong>Inputs:</strong> packet-level metadata only. Payload, URL
              and DNS content are never inspected.
            </p>
          </div>
        )}
      </section>

      <section className="model-intelligence-page__section">
        <h2>Recent Predictions</h2>
        <p className="model-intelligence-page__section-description">
          The latest classifications produced by the live inference loop.
        </p>
        <div className="inference-feed" role="table" aria-label="Recent predictions">
          <div className="inference-feed__header" role="row">
            <span role="columnheader">Time</span>
            <span role="columnheader">Detected application</span>
            <span role="columnheader">Class</span>
            <span role="columnheader">Confidence</span>
            <span role="columnheader">Latency</span>
          </div>
          {feed.map((entry) => (
            <div className="inference-feed__row" role="row" key={entry.id}>
              <span role="cell" className="inference-feed__time">
                {new Date(entry.time).toLocaleTimeString()}
              </span>
              <span role="cell">{entry.app}</span>
              <span role="cell">
                <StatusBadge variant="info" size="sm">
                  {(TRAFFIC_LABELS[entry.trafficClass] || entry.trafficClass).toUpperCase()}
                </StatusBadge>
              </span>
              <span role="cell" className="inference-feed__confidence">
                {entry.confidence.toFixed(1)}%
              </span>
              <span role="cell" className="inference-feed__latency">
                {entry.latency.toFixed(2)} ms
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="model-intelligence-page__section">
        <h2>Model Health</h2>
        <p className="model-intelligence-page__section-description">
          Continuous monitoring for drift, freshness and safe fallbacks.
        </p>
        <div className="model-cards-grid">
          {health.map((item) => (
            <div className="model-card" key={item.label}>
              <div className="model-card__header">
                <h3 className="model-card__name">{item.label}</h3>
                <StatusBadge variant={item.status} size="sm">
                  {item.status === "success" ? "HEALTHY" : "SCHEDULED"}
                </StatusBadge>
              </div>
              <div className="model-health-card__value">
                {item.value}
                <span className="model-health-card__unit">{item.unit}</span>
              </div>
              <p className="model-card__description">{item.detail}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function PipelineStageOrArrow({ stage, index }) {
  return (
    <>
      {index > 0 && <PipelineArrow />}
      <PipelineStage {...stage} />
    </>
  );
}

function ModelStat({ label, value, meta }) {
  return (
    <div className="model-stat">
      <span className="model-stat__label">{label}</span>
      <span className="model-stat__value">{value}</span>
      <span className="model-stat__meta">{meta}</span>
    </div>
  );
}

function PipelineStage({ name, status, description, note }) {
  return (
    <div className="pipeline-stage" role="group" aria-label={`${name} stage`}>
      <div className="pipeline-stage__header">
        <h3 className="pipeline-stage__name">{name}</h3>
        <StatusBadge variant={status === "live" ? "success" : "info"} size="sm">
          {status === "live" ? "LIVE" : "CONNECTED"}
        </StatusBadge>
      </div>
      <p className="pipeline-stage__description">{description}</p>
      <div className="pipeline-stage__meta">
        <span className="pipeline-stage__label">Live telemetry</span>
        <span className="pipeline-stage__value">{note}</span>
      </div>
    </div>
  );
}

function PipelineArrow() {
  return (
    <div className="pipeline-arrow" aria-hidden="true">
      <svg width="32" height="24" viewBox="0 0 32 24" fill="none">
        <path
          d="M0 12H28M28 12L20 4M28 12L20 20"
          stroke="var(--color-border-strong)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function ModelCard({ model }) {
  return (
    <article className="model-card">
      <div className="model-card__header">
        <h3 className="model-card__name">{model.name}</h3>
        <StatusBadge variant="success" size="sm">
          SERVING
        </StatusBadge>
      </div>
      <p className="model-card__description">
        {model.algorithm} · {model.version}
      </p>
      <dl className="model-card__metrics-grid">
        <div>
          <dt>Accuracy</dt>
          <dd>{model.accuracy.toFixed(1)}%</dd>
        </div>
        <div>
          <dt>Precision</dt>
          <dd>{model.precision.toFixed(1)}%</dd>
        </div>
        <div>
          <dt>Recall</dt>
          <dd>{model.recall.toFixed(1)}%</dd>
        </div>
      </dl>
      <dl className="model-card__meta">
        <div>
          <dt>Latency</dt>
          <dd>{model.latency.toFixed(2)} ms</dd>
        </div>
        <div>
          <dt>Inferences</dt>
          <dd>{model.inferences.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Last trained</dt>
          <dd>{model.lastTrained}</dd>
        </div>
      </dl>
    </article>
  );
}

export default ModelIntelligencePage;

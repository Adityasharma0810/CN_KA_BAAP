import { useState } from "react";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./ModelIntelligencePage.css";

/**
 * ModelIntelligencePage - ML pipeline status and model information.
 * All model metrics shown here are based on offline evaluation artifacts, not live inference.
 * Live classifier integration is NOT_STARTED in the current product path.
 */
export function ModelIntelligencePage() {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="model-intelligence-page">
      <header className="model-intelligence-page__header">
        <div className="model-intelligence-page__title-section">
          <h1>Model Intelligence</h1>
          <p className="model-intelligence-page__subtitle">
            Machine learning pipeline status and offline evaluation results.
          </p>
        </div>
      </header>

      <section className="model-intelligence-page__section model-intelligence-page__pipeline">
        <h2>ML Pipeline</h2>
        <p className="model-intelligence-page__section-description">
          The six-stage pipeline below shows the intended product architecture.
          Stages marked <StatusBadge variant="unknown" size="sm">NOT INTEGRATED</StatusBadge> are not connected to the live product
          decision path in the current checkout.
        </p>
        <div className="pipeline">
          <PipelineStage name="Observation" status="integrated" description="Collect telemetry via backend APIs" note="INTEGRATED" />
          <PipelineArrow />
          <PipelineStage name="Classification" status="unavailable" description="Classify traffic workloads" note="NOT_STARTED in product path" />
          <PipelineArrow />
          <PipelineStage name="Capacity Estimation" status="unavailable" description="Estimate available link capacity" note="NOT_STARTED in product path" />
          <PipelineArrow />
          <PipelineStage name="Forecasting" status="unavailable" description="Predict capacity changes" note="Offline artifacts only" />
          <PipelineArrow />
          <PipelineStage name="QoE Scoring" status="proxy" description="Score experience quality" note="Deterministic proxy; not validated subjective QoE" />
          <PipelineArrow />
          <PipelineStage name="Optimization" status="unavailable" description="Allocate resources fairly" note="Weighted allocation; not full max-min QoE optimizer" />
        </div>
      </section>

      <section className="model-intelligence-page__section model-intelligence-page__models">
        <h2>Offline Model Artifacts</h2>
        <p className="model-intelligence-page__section-description">
          The following saved artifacts exist under <code>machine_learning/saved_models/</code> and <code>experiments/capacity_forecasting/models/</code>.
          They were produced by offline training and evaluation. A saved artifact is not a live classifier.
        </p>
        <div className="model-cards-grid">
          <ArtifactCard
            name="Application traffic classifier"
            file="application_classifier_xgboost.joblib"
            algorithm="XGBoost"
            status="artifact_only"
            description="Classifies traffic by application type using XGBoost on packet-level metadata. Not integrated into the live product decision path."
          />
          <ArtifactCard
            name="VPN traffic classifier"
            file="vpn_classifier_random_forest.joblib"
            algorithm="Random Forest"
            status="artifact_only"
            description="Trained to distinguish VPN from unencrypted flows using flow-level statistics. Evaluation metrics not available in this session."
          />
          <ArtifactCard
            name="QoE predictor"
            file="qoe_predictor.joblib"
            algorithm="Unknown"
            status="artifact_only"
            description="A saved QoE predictor artifact. The live product uses the deterministic proxy scorer in ml/qoe/scorer.py, not this artifact."
          />
          <ArtifactCard
            name="Capacity forecaster"
            file="experiments/capacity_forecasting/models/best"
            algorithm="Holt-Winters / LightGBM"
            status="artifact_only"
            description="Offline capacity forecasting with multiple model variants. Not connected to the live estimator or confidence gate."
          />
        </div>
      </section>

      <section className="model-intelligence-page__section model-intelligence-page__features">
        <h2>QoE Proxy Scorer — Live Component</h2>
        <p className="model-intelligence-page__section-description">
          The only model currently integrated into the product decision path is the deterministic observation-only QoE proxy scorer (<code>ml/qoe/scorer.py</code>).
        </p>
        <div className="feature-importance">
          {PROXY_INPUTS.map((item) => <ProxyInput key={item.field} {...item} />)}
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
          <div className="model-intelligence-page__section-description" style={{ marginTop: "var(--space-4)" }}>
            <p><strong>Call/game:</strong> linear penalty on RTT, jitter, and packet loss. Score = 100 − 0.25×rtt − 1.5×jitter − 2.5×loss (call). Clamped 0–100.</p>
            <p><strong>Stream:</strong> throughput vs 8 Mbps target × stability. Requires 5 history samples. Missing samples = unknown score.</p>
            <p><strong>Bulk:</strong> throughput vs fair share. Requires measured capacity and active client count. Missing inputs = unknown score.</p>
            <p><strong>Limitations:</strong> no validated subjective QoE calibration; no application-specific tolerances; no user-perceived quality ground truth.</p>
          </div>
        )}
      </section>

      <section className="model-intelligence-page__section model-intelligence-page__limitations">
        <h2>Model Limitations</h2>
        <div className="limitation-notice">
          <StatusBadge variant="warning" size="lg">IMPORTANT</StatusBadge>
          <div className="limitation-notice__content">
            <p><strong>Saved artifacts ≠ live classifiers.</strong> Model files in <code>machine_learning/saved_models/</code> are offline training outputs. They are not loaded, invoked, or contributing to any live policy decision in the current backend startup path.</p>
            <p><strong>Privacy-safe features only.</strong> Any future classifier must use only packet-level metadata (sizes, timing, counts, direction, duration). Payload inspection, URL logging, DNS content, and browsing history are forbidden.</p>
            <p><strong>Lab-trained, not household-validated.</strong> Training data came from namespace lab flows (iperf3). Real household traffic will differ.</p>
            <p><strong>QoE scores are proxies.</strong> The live scorer produces deterministic estimates from observed counters. Subjective user experience depends on application-specific tolerances and factors outside the measurement scope.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

const PROXY_INPUTS = [
  { field: "rtt_ms", label: "RTT (latency)", category: "Network", used_by: "call, game" },
  { field: "rtt_variation_ms", label: "RTT variation (jitter)", category: "Network", used_by: "call, game" },
  { field: "packet_loss_percent", label: "Packet loss", category: "Network", used_by: "call" },
  { field: "download_mbps", label: "Download throughput", category: "Network", used_by: "stream, bulk" },
  { field: "measured_capacity_mbps", label: "Measured link capacity", category: "Derived", used_by: "bulk" },
  { field: "rate_stability_samples", label: "5-sample throughput history", category: "History", used_by: "stream" },
];

function ProxyInput({ field, label, category, used_by }) {
  return (
    <div className="feature-importance-row">
      <div className="feature-importance-label">
        <span className="feature-importance-name">{label}</span>
        <span className="feature-importance-category">{category} — used by: {used_by}</span>
      </div>
      <div className="feature-importance-bar-container">
        <div className="feature-importance-bar" style={{ width: "100%" }} role="img" aria-label={`Input field ${field}`}>
          <span className="feature-importance-value">{field}</span>
        </div>
      </div>
    </div>
  );
}

function PipelineStage({ name, status, description, note }) {
  return (
    <div className="pipeline-stage" role="group" aria-label={`${name} stage`}>
      <div className="pipeline-stage__header">
        <h3 className="pipeline-stage__name">{name}</h3>
        {status === "integrated" ? (
          <StatusBadge variant="success" size="sm">API INTEGRATED</StatusBadge>
        ) : status === "proxy" ? (
          <StatusBadge variant="warning" size="sm">LIVE PROXY</StatusBadge>
        ) : (
          <StatusBadge variant="unknown" size="sm">NOT INTEGRATED</StatusBadge>
        )}
      </div>
      <p className="pipeline-stage__description">{description}</p>
      <div className="pipeline-stage__meta">
        <span className="pipeline-stage__label">Status note</span>
        <span className="pipeline-stage__value">{note}</span>
      </div>
    </div>
  );
}

function PipelineArrow() {
  return (
    <div className="pipeline-arrow" aria-hidden="true">
      <svg width="32" height="24" viewBox="0 0 32 24" fill="none">
        <path d="M0 12H28M28 12L20 4M28 12L20 20" stroke="var(--color-border-strong)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

function ArtifactCard({ name, file, algorithm, description }) {
  return (
    <div className="model-card">
      <div className="model-card__header">
        <h3 className="model-card__name">{name}</h3>
        <StatusBadge variant="unknown" size="sm">ARTIFACT ONLY</StatusBadge>
      </div>
      <p className="model-card__description">{description}</p>
      <dl className="model-card__meta">
        <div><dt>Algorithm</dt><dd>{algorithm}</dd></div>
        <div><dt>File</dt><dd>{file}</dd></div>
        <div><dt>Live status</dt><dd>Not serving</dd></div>
      </dl>
    </div>
  );
}

export default ModelIntelligencePage;

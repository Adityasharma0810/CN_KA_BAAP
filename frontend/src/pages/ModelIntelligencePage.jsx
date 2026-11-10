import { useState } from "react";
import { StatusBadge, StatusBadges } from "../components/ui/StatusBadge";
import "./ModelIntelligencePage.css";

/**
 * ModelIntelligencePage - ML Pipeline visualization, model cards, and feature importance
 * Shows the machine learning components that power Experience Budget
 */
export function ModelIntelligencePage() {
  // Static mock data - will be replaced with real ML model status and metrics
  const [pipelineStatus] = useState({
    observation: { status: "active", lastUpdate: "2026-11-10T09:15:32Z" },
    classification: { status: "active", lastUpdate: "2026-11-10T09:15:33Z" },
    capacityEstimation: { status: "active", lastUpdate: "2026-11-10T09:15:34Z" },
    forecasting: { status: "active", lastUpdate: "2026-11-10T09:15:35Z" },
    qoeScoring: { status: "active", lastUpdate: "2026-11-10T09:15:36Z" },
    optimization: { status: "active", lastUpdate: "2026-11-10T09:15:37Z" },
  });

  const [modelCards] = useState([
    {
      name: "Traffic Classifier",
      version: "1.2.0",
      type: "Random Forest",
      status: "active",
      trainedDate: "2026-10-15",
      accuracy: 0.87,
      precision: 0.85,
      recall: 0.89,
      description: "Classifies traffic flows into broad workload categories using privacy-safe metadata",
    },
    {
      name: "Capacity Estimator",
      version: "1.1.0",
      type: "LSTM",
      status: "active",
      trainedDate: "2026-10-20",
      accuracy: 0.82,
      precision: 0.80,
      recall: 0.84,
      description: "Estimates available link capacity and uncertainty using recent throughput observations",
    },
    {
      name: "QoE Scorer",
      version: "2.0.0",
      type: "Ensemble",
      status: "active",
      trainedDate: "2026-10-25",
      accuracy: 0.91,
      precision: 0.90,
      recall: 0.92,
      description: "Scores workload-specific quality of experience based on latency, jitter, loss, and throughput",
    },
  ]);

  const [featureImportance] = useState([
    { feature: "Latency P95", importance: 0.28, category: "Network" },
    { feature: "Jitter", importance: 0.22, category: "Network" },
    { feature: "Packet Loss Rate", importance: 0.18, category: "Network" },
    { feature: "Download Throughput", importance: 0.15, category: "Network" },
    { feature: "Flow Duration", importance: 0.08, category: "Traffic" },
    { feature: "Packet Size Distribution", importance: 0.05, category: "Traffic" },
    { feature: "Inter-arrival Time", importance: 0.04, category: "Traffic" },
  ]);

  return (
    <div className="model-intelligence-page">
      {/* Page Header */}
      <header className="model-intelligence-page__header">
        <div className="model-intelligence-page__title-section">
          <h1>Model Intelligence</h1>
          <p className="model-intelligence-page__subtitle">
            Machine learning pipeline, model performance, and feature analysis
          </p>
        </div>
      </header>

      {/* ML Pipeline Visualization */}
      <section className="model-intelligence-page__section model-intelligence-page__pipeline">
        <h2>ML Pipeline</h2>
        <p className="model-intelligence-page__section-description">
          Experience Budget uses a multi-stage machine learning pipeline to classify traffic, estimate capacity, score QoE, and optimize resource allocation.
        </p>
        <div className="pipeline">
          <PipelineStage
            name="Observation"
            status={pipelineStatus.observation.status}
            lastUpdate={pipelineStatus.observation.lastUpdate}
            description="Collect network telemetry"
          />
          <PipelineArrow />
          <PipelineStage
            name="Classification"
            status={pipelineStatus.classification.status}
            lastUpdate={pipelineStatus.classification.lastUpdate}
            description="Identify traffic workloads"
          />
          <PipelineArrow />
          <PipelineStage
            name="Capacity Estimation"
            status={pipelineStatus.capacityEstimation.status}
            lastUpdate={pipelineStatus.capacityEstimation.lastUpdate}
            description="Estimate link capacity"
          />
          <PipelineArrow />
          <PipelineStage
            name="Forecasting"
            status={pipelineStatus.forecasting.status}
            lastUpdate={pipelineStatus.forecasting.lastUpdate}
            description="Predict capacity changes"
          />
          <PipelineArrow />
          <PipelineStage
            name="QoE Scoring"
            status={pipelineStatus.qoeScoring.status}
            lastUpdate={pipelineStatus.qoeScoring.lastUpdate}
            description="Score experience quality"
          />
          <PipelineArrow />
          <PipelineStage
            name="Optimization"
            status={pipelineStatus.optimization.status}
            lastUpdate={pipelineStatus.optimization.lastUpdate}
            description="Allocate resources fairly"
          />
        </div>
      </section>

      {/* Model Cards */}
      <section className="model-intelligence-page__section model-intelligence-page__models">
        <h2>Model Cards</h2>
        <p className="model-intelligence-page__section-description">
          Performance metrics and metadata for each machine learning model in the pipeline.
        </p>
        <div className="model-cards-grid">
          {modelCards.map((model) => (
            <ModelCard key={model.name} model={model} />
          ))}
        </div>
      </section>

      {/* Feature Importance */}
      <section className="model-intelligence-page__section model-intelligence-page__features">
        <h2>Feature Importance</h2>
        <p className="model-intelligence-page__section-description">
          Relative importance of input features for traffic classification and QoE scoring.
        </p>
        <div className="feature-importance">
          {featureImportance.map((feature) => (
            <FeatureImportanceBar key={feature.feature} feature={feature} />
          ))}
        </div>
      </section>

      {/* Model Limitations */}
      <section className="model-intelligence-page__section model-intelligence-page__limitations">
        <h2>Model Limitations</h2>
        <div className="limitation-notice">
          <StatusBadge variant="warning" size="lg">IMPORTANT</StatusBadge>
          <div className="limitation-notice__content">
            <p><strong>Privacy-Safe Classification:</strong> Models use only privacy-safe metadata (packet sizes, inter-arrival times, flow duration). No payload inspection, no deep packet inspection, no URL/DNS logging.</p>
            <p><strong>Broad Categories Only:</strong> Classification identifies broad workload types (VoIP, streaming, gaming, bulk transfer) with confidence scores. It does not identify specific applications, services, or user intent.</p>
            <p><strong>Lab-Trained Models:</strong> Current models are trained on simulated lab data. Real-world household traffic may exhibit different patterns.</p>
            <p><strong>No Guarantees:</strong> QoE scores are estimates. Actual user-perceived quality depends on application-specific tolerances, device capabilities, and human factors outside the model's scope.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

/* Pipeline Stage Component */
function PipelineStage({ name, status, lastUpdate, description }) {
  return (
    <div className="pipeline-stage" role="group" aria-label={`${name} stage`}>
      <div className="pipeline-stage__header">
        <h3 className="pipeline-stage__name">{name}</h3>
        {status === "active" ? (
          <StatusBadges.ModelActive size="sm" />
        ) : (
          <StatusBadges.ModelUnavailable size="sm" />
        )}
      </div>
      <p className="pipeline-stage__description">{description}</p>
      <div className="pipeline-stage__meta">
        <span className="pipeline-stage__label">Last Update:</span>
        <span className="pipeline-stage__value">
          {new Date(lastUpdate).toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
}

/* Pipeline Arrow Component */
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

/* Model Card Component */
function ModelCard({ model }) {
  return (
    <div className="model-card">
      <div className="model-card__header">
        <h3 className="model-card__name">{model.name}</h3>
        {model.status === "active" ? (
          <StatusBadge variant="success" size="sm">ACTIVE</StatusBadge>
        ) : (
          <StatusBadge variant="failure" size="sm">UNAVAILABLE</StatusBadge>
        )}
      </div>
      <p className="model-card__description">{model.description}</p>
      <dl className="model-card__meta">
        <div>
          <dt>Type</dt>
          <dd>{model.type}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{model.version}</dd>
        </div>
        <div>
          <dt>Trained</dt>
          <dd>{new Date(model.trainedDate).toLocaleDateString()}</dd>
        </div>
      </dl>
      <div className="model-card__metrics">
        <h4>Performance Metrics</h4>
        <dl className="model-card__metrics-grid">
          <div>
            <dt>Accuracy</dt>
            <dd>{(model.accuracy * 100).toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Precision</dt>
            <dd>{(model.precision * 100).toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Recall</dt>
            <dd>{(model.recall * 100).toFixed(1)}%</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

/* Feature Importance Bar Component */
function FeatureImportanceBar({ feature }) {
  const percentage = (feature.importance * 100).toFixed(1);
  const widthPercentage = Math.max(percentage, 5); // Minimum 5% width for visibility

  return (
    <div className="feature-importance-row">
      <div className="feature-importance-label">
        <span className="feature-importance-name">{feature.feature}</span>
        <span className="feature-importance-category">{feature.category}</span>
      </div>
      <div className="feature-importance-bar-container">
        <div
          className="feature-importance-bar"
          style={{ width: `${widthPercentage}%` }}
          role="progressbar"
          aria-valuenow={feature.importance}
          aria-valuemin="0"
          aria-valuemax="1"
          aria-label={`${feature.feature} importance: ${percentage}%`}
        >
          <span className="feature-importance-value">{percentage}%</span>
        </div>
      </div>
    </div>
  );
}

export default ModelIntelligencePage;

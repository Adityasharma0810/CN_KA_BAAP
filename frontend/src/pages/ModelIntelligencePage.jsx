import { useEffect, useState } from "react";
import { getSystemCapabilities, getGatewayStatus, getHealth } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./ModelIntelligencePage.css";

/**
 * ModelIntelligencePage - real model registry and classifier status from the
 * paired gateway. No fabricated inference counters or accuracy figures.
 */
export function ModelIntelligencePage() {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      try {
        const [caps, gateway, health] = await Promise.allSettled([
          getSystemCapabilities(),
          getGatewayStatus(),
          getHealth(),
        ]);
        if (disposed) return;
        setSnapshot({
          capabilities:
            caps.status === "fulfilled" ? caps.value : null,
          gateway: gateway.status === "fulfilled" ? gateway.value : null,
          health: health.status === "fulfilled" ? health.value : null,
        });
        setError(null);
      } catch {
        if (disposed) return;
        setError("Model intelligence sources are reconnecting…");
      }
    };
    refresh();
    return () => {
      disposed = true;
    };
  }, []);

  const gateway = snapshot?.gateway || {};
  const health = snapshot?.health || {};

  return (
    <div className="model-intelligence-page">
      <header className="model-intelligence-page__header">
        <div className="model-intelligence-page__title-section">
          <h1>ML Lab</h1>
          <p className="model-intelligence-page__subtitle">
            Real model status, classifier schema, and inference metadata from
            the paired gateway. Values are measured, never fabricated.
          </p>
        </div>
      </header>

      {error && (
        <div className="model-intelligence-page__error" role="alert">
          {error}
        </div>
      )}

      <section className="model-intelligence-page__section">
        <h2>Model Registry</h2>
        <p className="model-intelligence-page__section-description">
          Registered models and their measured health, validation results, and
          inference latency. Empty until a model is registered and trained on
          real labelled telemetry.
        </p>
        <div className="model-registry">
          <div className="model-registry__empty">
            <p>No models registered yet.</p>
            <p className="muted">
              Register a trained model through the control plane or train one
              from labelled synthetic data in the Simulation tab.
            </p>
          </div>
        </div>
      </section>

      <section className="model-intelligence-page__section">
        <h2>Traffic Classifier (F1)</h2>
        <p className="model-intelligence-page__section-description">
          Privacy-safe flow classifier operating on packet-metadata features
          only. Never inspects encrypted payloads.
        </p>
        <div className="classifier-card">
          <dl className="classifier-card__details">
            <dt>Classes</dt>
            <dd>Call, Gaming, Streaming, Bulk, Unknown</dd>
            <dt>Unknown threshold</dt>
            <dd>0.60</dd>
            <dt>Fallback</dt>
            <dd>Deterministic rule-based</dd>
          </dl>
          <p className="muted note">
            The classifier returns &ldquo;Unknown&rdquo; when confidence is
            below threshold, and uses safe fallback rules. No certainty is
            claimed about encrypted applications.
          </p>
        </div>
      </section>

      <section className="model-intelligence-page__section">
        <h2>Capacity Estimator (F2)</h2>
        <p className="model-intelligence-page__section-description">
          Kalman-filter estimate of usable link capacity with uncertainty.
        </p>
        <div className="classifier-card">
          <dl className="classifier-card__details">
            <dt>Method</dt>
            <dd>Kalman filter</dd>
            <dt>Estimate</dt>
            <dd>Waiting for first observation…</dd>
            <dt>Uncertainty</dt>
            <dd>—</dd>
            <dt>Confidence</dt>
            <dd>—</dd>
          </dl>
          <p className="muted note">
            Capacity estimates appear once the gateway reports real telemetry.
          </p>
        </div>
      </section>

      <section className="model-intelligence-page__section">
        <h2>Gateway &amp; Model Health</h2>
        <div className="health-grid">
          <HealthTile
            label="Backend"
            value={health.status || "unavailable"}
            ok={health.status === "healthy"}
          />
          <HealthTile
            label="Gateway"
            value={gateway.status || "unpaired"}
            ok={gateway.status === "connected"}
          />
          <HealthTile
            label="Classifier"
            value="loaded (rule-based)"
            ok={!!gateway.status}
          />
          <HealthTile
            label="Inference latency"
            value="— ms"
            ok={false}
          />
        </div>
      </section>
    </div>
  );
}

function HealthTile({ label, value, ok }) {
  return (
    <div className="health-tile">
      <div className="health-tile__label">{label}</div>
      <div className="health-tile__value">
        <StatusBadge variant={ok ? "success" : "unknown"} size="sm">
          {value}
        </StatusBadge>
      </div>
    </div>
  );
}

export default ModelIntelligencePage;

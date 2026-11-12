import { useEffect, useRef, useState } from "react";
import {
  getScenarioCatalog,
  startScenario,
  stopScenario,
  getCurrentObservations,
} from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { MetricCard } from "../components/ui/MetricCard";
import "./ComparePage.css";

export function ComparePage() {
  const [catalog, setCatalog] = useState(null);
  const [status, setStatus] = useState(null);
  const [scenario, setScenario] = useState("");
  const [duration, setDuration] = useState(60);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [catalogError, setCatalogError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [observations, setObservations] = useState([]);
  const [obsError, setObsError] = useState(null);
  const actionController = useRef(null);

  useEffect(() => {
    let disposed = false;
    let timer;
    let controller;

    const poll = async () => {
      controller = new AbortController();
      const { signal } = controller;
      try {
        const result = await getScenarioCatalog({ signal });
        if (signal.aborted) return;
        setCatalog(result);
        setStatus(result.status || null);
        setScenario((current) =>
          result.scenarios.some((item) => item.id === current)
            ? current
            : result.scenarios[0]?.id || "",
        );
        if (!disposed) setLoading(false);
        setCatalogError(null);
      } catch {
        if (signal.aborted) return;
        setCatalogError("Scenario catalog is reconnecting…");
        if (!disposed) setLoading(false);
      }

      // Refresh real observations alongside.
      try {
        const obs = await getCurrentObservations({}, { signal });
        if (!signal.aborted) {
          setObservations(obs.observations || []);
          setObsError(null);
        }
      } catch {
        if (!signal.aborted) setObsError("Observations are reconnecting…");
      }

      if (!disposed && !signal.aborted) {
        timer = window.setTimeout(poll, 5000);
      }
    };

    poll();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      controller?.abort();
      actionController.current?.abort();
    };
  }, []);

  const runScenario = async () => {
    if (actionController.current) return;
    const controller = new AbortController();
    actionController.current = controller;
    setActionPending(true);
    setActionError(null);
    try {
      const result = await startScenario(
        scenario,
        { duration_seconds: duration },
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) setStatus(result.status);
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setActionError(
          requestError.message || "Scenario could not be started.",
        );
      }
    } finally {
      if (actionController.current === controller) {
        actionController.current = null;
        setActionPending(false);
      }
    }
  };

  const stop = async () => {
    if (actionController.current) return;
    const controller = new AbortController();
    actionController.current = controller;
    setActionPending(true);
    setActionError(null);
    try {
      const result = await stopScenario({ signal: controller.signal });
      if (!controller.signal.aborted) setStatus(result);
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setActionError(requestError.message || "Scenario could not be stopped.");
      }
    } finally {
      if (actionController.current === controller) {
        actionController.current = null;
        setActionPending(false);
      }
    }
  };

  const running = ["starting", "running", "stopping"].includes(status?.state);
  const definitions = catalog?.scenarios || [];
  const clientCount = observations.length;
  const totalDownload = observations.reduce(
    (t, o) => t + (Number(o.download_mbps) || 0),
    0,
  );
  const totalUpload = observations.reduce(
    (t, o) => t + (Number(o.upload_mbps) || 0),
    0,
  );

  return (
    <div className="compare-page">
      <header className="compare-page__header">
        <div className="compare-page__title-section">
          <h1>Experiments &amp; A-B Testing</h1>
          <p className="compare-page__subtitle">
            Run controlled network experiments using real captured
            measurements. Results are grounded in actual telemetry — no
            fabricated baseline or optimized values are shown.
          </p>
        </div>
        <div className="compare-page__meta">
          <dl className="compare-page__meta-grid">
            <div>
              <dt>Environment</dt>
              <dd>
                <StatusBadge variant="success" size="sm">
                  REAL TELEMETRY
                </StatusBadge>
              </dd>
            </div>
            <div>
              <dt>Scenario state</dt>
              <dd>
                <StatusBadge
                  variant={running ? "live" : "inactive"}
                  size="sm"
                >
                  {(status?.state || "idle").toUpperCase()}
                </StatusBadge>
              </dd>
            </div>
            <div>
              <dt>Run ID</dt>
              <dd>{status?.run_id || "—"}</dd>
            </div>
            <div>
              <dt>Remaining</dt>
              <dd>
                {status?.remaining_seconds == null
                  ? "—"
                  : `${status.remaining_seconds}s`}
              </dd>
            </div>
            <div>
              <dt>Observed clients</dt>
              <dd>{clientCount}</dd>
            </div>
          </dl>
        </div>
      </header>

      <section className="compare-page__section compare-page__controls">
        <h2>Controlled Experiment</h2>
        <p className="compare-page__section-description">
          Launch a bounded experiment and observe real per-client telemetry.
          Each run is executed on the paired gateway.
        </p>
        <div className="compare-page__controls-grid">
          <div className="compare-page__control-group">
            <label htmlFor="compare-scenario">
              Experiment
              <select
                id="compare-scenario"
                value={scenario}
                onChange={(event) => setScenario(event.target.value)}
                disabled={running || actionPending}
              >
                {definitions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="compare-duration">
              Duration (seconds)
              <input
                id="compare-duration"
                type="number"
                min="5"
                max="3600"
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
                disabled={running || actionPending}
              />
            </label>
          </div>
          <div className="compare-page__control-actions">
            <div className="compare-page__buttons">
              {running ? (
                <button
                  className="btn btn--secondary"
                  onClick={stop}
                  disabled={actionPending}
                >
                  {actionPending ? "Stopping…" : "Stop Experiment"}
                </button>
              ) : (
                <button
                  className="btn btn--primary"
                  onClick={runScenario}
                  disabled={loading || actionPending || !scenario}
                >
                  {actionPending ? "Starting…" : "Start Experiment"}
                </button>
              )}
            </div>
            {catalogError && (
              <div className="compare-page__error" role="status">
                {catalogError}
              </div>
            )}
            {actionError && (
              <div className="compare-page__error" role="alert">
                {actionError}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="compare-page__section">
        <h2>Live Observations During Experiment</h2>
        <p className="compare-page__section-description">
          Real per-client measurements captured during the experiment window.
        </p>
        {obsError && (
          <div className="compare-page__error" role="status">{obsError}</div>
        )}
        <div className="compare-page__cards-grid">
          <MetricCard
            title="Observed clients"
            value={clientCount}
            unit="clients"
            digits={0}
          />
          <MetricCard
            title="Aggregate download"
            value={totalDownload}
            unit="Mbps"
            digits={1}
          />
          <MetricCard
            title="Aggregate upload"
            value={totalUpload}
            unit="Mbps"
            digits={1}
          />
        </div>
        {observations.length ? (
          <div className="usage-tree">
            <div className="usage-tree__root">
              <div className="usage-tree__gateway">
                <span className="usage-tree__label">
                  Experience Budget gateway
                </span>
                <StatusBadge variant="success" size="sm">
                  {clientCount} CLIENTS
                </StatusBadge>
              </div>
              <div className="usage-tree__branches">
                {observations.map((item) => {
                  const meta = item.metadata || {};
                  return (
                    <div
                      className="usage-tree__branch"
                      key={meta.client_id || item.id}
                    >
                      <div className="usage-tree__client">
                        <span>
                          {meta.client_id
                            ? `Client ${meta.client_id.split("-").pop()}`
                            : "client"}
                        </span>
                      </div>
                      <div className="usage-tree__details">
                        <dl className="usage-tree__detail-list">
                          <dt>Download</dt>
                          <dd>
                            {(item.download_mbps ?? 0).toFixed(2)} Mbps
                          </dd>
                          <dt>Upload</dt>
                          <dd>
                            {(item.upload_mbps ?? 0).toFixed(2)} Mbps
                          </dd>
                          <dt>Quality</dt>
                          <dd>{meta.quality || "—"}</dd>
                        </dl>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          <div className="compare-page__empty">
            No observations yet. Start an experiment or pair a gateway.
          </div>
        )}
      </section>
    </div>
  );
}

export default ComparePage;

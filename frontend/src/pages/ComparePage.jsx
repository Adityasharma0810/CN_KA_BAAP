import { useEffect, useRef, useState } from "react";
import {
  getComparison,
  getScenarioCatalog,
  startScenario,
  stopScenario,
} from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { MetricCard } from "../components/ui/MetricCard";
import { MultiMetricComparisonChart } from "../components/charts/ComparisonChart";
import "./ComparePage.css";

const CHART_METRICS = [
  { key: "latency", unit: "ms", digits: 1, label: "Latency (RTT)" },
  { key: "jitter", unit: "ms", digits: 1, label: "Jitter" },
  { key: "loss", unit: "%", digits: 2, label: "Packet loss" },
  { key: "download", unit: "Mbps", digits: 1, label: "Download throughput" },
  { key: "upload", unit: "Mbps", digits: 1, label: "Upload throughput" },
  { key: "qoe", unit: "/100", digits: 1, label: "QoE score" },
];

const TRAFFIC_LABELS = {
  call: "Voice / video call",
  game: "Cloud gaming",
  stream: "Video streaming",
  bulk: "Bulk transfer",
};

export function ComparePage() {
  const [catalog, setCatalog] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [scenario, setScenario] = useState("");
  const [duration, setDuration] = useState(60);
  const [seed, setSeed] = useState(42);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [catalogError, setCatalogError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const actionController = useRef(null);

  useEffect(() => {
    let disposed = false;
    let timer;
    let controller;

    const poll = async () => {
      controller = new AbortController();
      const { signal } = controller;
      const [catalogResult, comparisonResult] = await Promise.allSettled([
        getScenarioCatalog({ signal }),
        getComparison({ signal }),
      ]);
      if (signal.aborted) return;

      if (catalogResult.status === "fulfilled") {
        const result = catalogResult.value;
        setCatalog(result);
        setStatus(result.status || null);
        setScenario((current) =>
          result.scenarios.some((item) => item.id === current)
            ? current
            : result.scenarios[0]?.id || "",
        );
        setCatalogError(null);
        setLoading(false);
      } else {
        setCatalogError("Scenario catalog is reconnecting…");
        setLoading(false);
      }

      if (comparisonResult.status === "fulfilled") {
        setComparison(comparisonResult.value);
      }

      if (!disposed && !signal.aborted) {
        timer = window.setTimeout(poll, 1000);
      }
    };

    poll();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      controller?.abort();
      actionController.current?.abort();
      actionController.current = null;
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
        { duration_seconds: duration, seed },
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setStatus(result.status);
      }
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setActionError(getScenarioActionError(requestError));
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
      if (!controller.signal.aborted) {
        setStatus(result);
      }
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setActionError(getScenarioActionError(requestError));
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
  const activeDefinition = definitions.find((item) => item.id === scenario);
  const metrics = comparison?.metrics || [];
  const household = comparison?.household || [];
  const findings = comparison?.conclusion?.findings || [];

  return (
    <div className="compare-page">
      <header className="compare-page__header">
        <div className="compare-page__title-section">
          <h1>Network Experience Comparison</h1>
          <p className="compare-page__subtitle">
            Baseline versus Experience Budget, measured live on the household
            lab. Charts and conclusions update every second.
          </p>
        </div>
        <div className="compare-page__meta">
          <dl className="compare-page__meta-grid">
            <div>
              <dt>Source</dt>
              <dd>
                <StatusBadge variant="simulated" size="sm">
                  SIMULATED LAB · LIVE
                </StatusBadge>
              </dd>
            </div>
            <div>
              <dt>Scenario state</dt>
              <dd>
                <StatusBadge variant={running ? "live" : "inactive"} size="sm">
                  {(status?.state || "idle").toUpperCase()}
                </StatusBadge>
              </dd>
            </div>
            <div>
              <dt>Run ID</dt>
              <dd>{status?.run_id || "Run queue ready"}</dd>
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
              <dt>Last sample</dt>
              <dd>
                {comparison?.observed_at
                  ? new Date(comparison.observed_at).toLocaleTimeString()
                  : "Syncing…"}
              </dd>
            </div>
          </dl>
        </div>
      </header>

      <section className="compare-page__section compare-page__controls">
        <h2>Scenario Lab</h2>
        <p className="compare-page__section-description">
          Launch a bounded lab run and watch both baselines converge in real
          time. Every repeat is seeded so results stay comparable.
        </p>
        <div className="compare-page__controls-grid">
          <div className="compare-page__control-group">
            <label htmlFor="compare-scenario">
              Scenario
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
                max="120"
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
                disabled={running || actionPending}
              />
            </label>
            <label htmlFor="compare-seed">
              Seed
              <input
                id="compare-seed"
                type="number"
                min="0"
                max="2147483647"
                value={seed}
                onChange={(event) => setSeed(Number(event.target.value))}
                disabled={running || actionPending}
              />
            </label>
          </div>
          <div className="compare-page__control-actions">
            <div className="compare-page__seed-indicator">
              <StatusBadge variant="live" size="sm">
                ● LIVE DEMO
              </StatusBadge>
              <span className="compare-page__vs">
                {activeDefinition?.description ||
                  "Select a scenario to preview its workload."}
              </span>
            </div>
            <div className="compare-page__buttons">
              {running ? (
                <button
                  className="btn btn--secondary"
                  onClick={stop}
                  disabled={actionPending}
                >
                  {actionPending ? "Stopping…" : "Stop Scenario"}
                </button>
              ) : (
                <button
                  className="btn btn--primary"
                  onClick={runScenario}
                  disabled={loading || actionPending || !scenario}
                >
                  {actionPending ? "Starting…" : "Start Scenario"}
                </button>
              )}
            </div>
          </div>
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
      </section>

      <section className="compare-page__section">
        <h2>Metric comparison</h2>
        <p className="compare-page__section-description">
          Live baseline versus Experience Budget across the six experience
          metrics. The change column is computed from the most recent sample.
        </p>
        <div className="compare-page__cards-grid">
          {metrics.map((metric) => (
            <MetricCard
              key={metric.key}
              title={metric.label}
              baselineValue={metric.baseline}
              optimizedValue={metric.optimized}
              unit={metric.unit}
              digits={metric.key === "loss" ? 2 : 1}
              lowerIsBetter={metric.lowerIsBetter}
              showProvenance={false}
            />
          ))}
        </div>
      </section>

      <section className="compare-page__section compare-page__charts">
        <h2>Time-series comparison</h2>
        <p className="compare-page__section-description">
          The last 60 one-second samples for latency, jitter, loss, throughput
          and QoE. Dashed lines are the untreated baseline.
        </p>
        <MultiMetricComparisonChart
          data={comparison?.series || []}
          metrics={CHART_METRICS}
          height={220}
        />
      </section>

      <section className="compare-page__section">
        <h2>Household usage tree</h2>
        <p className="compare-page__section-description">
          Every connected client, its live class and the policy currently
          protecting its experience.
        </p>
        <div className="usage-tree">
          <div className="usage-tree__root">
            <div className="usage-tree__gateway">
              <span className="usage-tree__icon" aria-hidden="true">
                ⬡
              </span>
              <span className="usage-tree__label">
                Experience Budget gateway
              </span>
              <StatusBadge variant="success" size="sm">
                ONLINE · {household.length} CLIENTS
              </StatusBadge>
            </div>
            <div className="usage-tree__branches">
              {household.map((client) => (
                <div className="usage-tree__branch" key={client.id}>
                  <div className="usage-tree__client">
                    <span>{client.label}</span>
                    <StatusBadge
                      variant={client.trafficClass === "bulk" ? "warning" : "success"}
                      size="sm"
                    >
                      {client.policy.toUpperCase()}
                    </StatusBadge>
                  </div>
                  <div className="usage-tree__details">
                    <dl className="usage-tree__detail-list">
                      <dt>Traffic class</dt>
                      <dd>
                        {TRAFFIC_LABELS[client.trafficClass] ||
                          client.trafficClass}
                      </dd>
                      <dt>Download</dt>
                      <dd>{client.download.toFixed(1)} Mbps</dd>
                      <dt>Upload</dt>
                      <dd>{client.upload.toFixed(1)} Mbps</dd>
                      <dt>Latency</dt>
                      <dd>{client.rtt.toFixed(1)} ms</dd>
                      <dt>Jitter</dt>
                      <dd>{client.jitter.toFixed(1)} ms</dd>
                      <dt>QoE</dt>
                      <dd>
                        {client.qoe.toFixed(1)}/100{" "}
                        <span className="usage-tree__confidence">
                          {client.loss.toFixed(2)}% loss
                        </span>
                      </dd>
                    </dl>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="compare-page__section">
        <h2>Conclusion</h2>
        <p className="compare-page__section-description">
          Automated summary from the current run window.
        </p>
        <div className="conclusion-panel">
          <div className="conclusion-panel__overall">
            <StatusBadge variant="success" size="lg">
              VERIFIED
            </StatusBadge>
            <p>
              {comparison?.conclusion?.overall ||
                "Collecting samples for the current run…"}
            </p>
          </div>
          <dl className="conclusion-panel__findings">
            {findings.map((finding) => (
              <div className="conclusion-panel__finding" key={finding.label}>
                <dt>{finding.label}</dt>
                <dd>
                  <StatusBadge variant={finding.variant} size="sm">
                    {finding.value}
                  </StatusBadge>
                  <span>{finding.detail}</span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}

function getScenarioActionError(error) {
  if (error.code === "helper_missing") {
    return error.installCommand
      ? `Scenario Lab could not run its restricted helper. From the repository root, run "${error.installCommand}" with administrator authorization, then restart the backend.`
      : "Scenario Lab could not run its restricted helper. Ask an administrator to install the project helper, then restart the backend.";
  }
  return error.message;
}

export default ComparePage;

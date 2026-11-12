import * as demo from "../api/demoData";
import { useState } from "react";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./SimulationPage.css";

/**
 * Simulation - the ONLY tab allowed to show simulated household data.
 * All simulated observations carry environment=simulated_lab and are never
 * merged into production telemetry.
 */
export function SimulationPage() {
  const cat = demo.getScenarioCatalog();
  const [comparison, setComparison] = useState(null);
  const [status, setStatus] = useState(null);
  const [selectedScenario, setSelectedScenario] = useState(
    cat.scenarios[0]?.id || ""
  );
  const [duration, setDuration] = useState(60);
  const [seed, setSeed] = useState(42);

  const defs = cat.scenarios;
  const running = ["starting", "running", "stopping"].includes(status?.state);

  const runScenario = () => {
    const res = demo.startScenario(selectedScenario, {
      duration_seconds: duration,
      seed,
    });
    setStatus(res.status);
    setTimeout(() => {
      setComparison(demo.getComparison());
    }, 500);
  };

  return (
    <div className="simulation-page">
      <header className="page-header sim-header">
        <h1>Simulation</h1>
        <p className="subtitle">
          Isolated virtual lab. All data here is synthetic and carries
          <code>environment=simulated_lab</code>. It is never shown in the
          production dashboard or merged into real telemetry.
        </p>
        <StatusBadge variant="simulated" size="sm">SIMULATED LAB</StatusBadge>
      </header>

      <section className="sim-section">
        <h2>Scenario Lab</h2>
        <p className="sim-desc">
          Synthetic topologies, configurable bandwidth, and synthetic call,
          gaming, streaming, and bulk traffic.
        </p>
        <div className="sim-controls">
          <div className="sim-form">
            <label>Scenario</label>
            <select
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              disabled={running}
            >
              {defs.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <label>Duration (s)</label>
            <input
              type="number"
              min="5"
              max="3600"
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              disabled={running}
            />
            <label>Seed</label>
            <input
              type="number"
              min="0"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              disabled={running}
            />
            <div className="sim-actions">
              <button
                className="btn btn--primary"
                onClick={runScenario}
                disabled={running || !selectedScenario}
              >
                {running ? "Stop scenario" : "Start scenario"}
              </button>
              <button
                className="btn btn--secondary"
                onClick={() => {
                  demo.stopScenario();
                  setStatus(demo.stopScenario().status);
                  setComparison(null);
                }}
                disabled={!running}
              >
                Stop
              </button>
            </div>
          </div>
          <div className="sim-status">
            <span className="label">State</span>
            <StatusBadge
              variant={running ? "live" : "inactive"}
              size="sm"
            >
              {(status?.state || "idle").toUpperCase()}
            </StatusBadge>
            <span className="label">Run ID</span>
            <span>{status?.run_id || "—"}</span>
            <span className="label">Remaining</span>
            <span>{status?.remaining_seconds ?? "—"}s</span>
          </div>
        </div>
      </section>

      {comparison && (
        <section className="sim-section">
          <h2>Results (synthetic)</h2>
          <div className="sim-results">
            <div className="sim-result-card">
              <div className="sim-result__label">Source</div>
              <div className="sim-result__value">{comparison.source}</div>
            </div>
            <div className="sim-result-card">
              <div className="sim-result__label">Scenario</div>
              <div className="sim-result__value">
                {comparison.scenario || "—"}
              </div>
            </div>
            <div className="sim-result-card">
              <div className="sim-result__label">Run ID</div>
              <div className="sim-result__value">
                {comparison.run_id || "—"}
              </div>
            </div>
          </div>
          <div className="sim-table">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Optimized</th>
                  <th>Unit</th>
                </tr>
              </thead>
              <tbody>
                {comparison.metrics.map((m) => (
                  <tr key={m.key}>
                    <td>{m.label}</td>
                    <td className="numeric">{m.baseline}</td>
                    <td className="numeric">{m.optimized}</td>
                    <td>{m.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="sim-household">
            <h3>Household (synthetic)</h3>
            <div className="sim-household__list">
              {comparison.household.map((c) => (
                <div key={c.id} className="sim-household__item">
                  <div>
                    <div className="sim-household__name">{c.label}</div>
                    <div className="sim-household__class">{c.trafficClass}</div>
                  </div>
                  <div className="sim-household__metrics">
                    <span>{c.download.toFixed(1)} down</span>
                    <span>{c.upload.toFixed(1)} up</span>
                    <span>{c.qoe.toFixed(0)} QoE</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <div className="sim-warning">
        <strong>Note:</strong> Everything in this tab is simulated. Real
        measurements appear in Overview, Live Metrics, Devices, and the other
        production tabs once a gateway is paired.
      </div>
    </div>
  );
}

export default SimulationPage;

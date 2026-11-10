import { useCallback, useEffect, useState } from "react";
import { getScenarioCatalog, startScenario, stopScenario } from "../api/client";
import { StatusBadge, StatusBadges } from "../components/ui/StatusBadge";
import "./ComparePage.css";

export function ComparePage() {
  const [catalog, setCatalog] = useState(null);
  const [scenario, setScenario] = useState("call_vs_download");
  const [duration, setDuration] = useState(60);
  const [seed, setSeed] = useState(42);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async (signal) => {
    try {
      const result = await getScenarioCatalog({ signal });
      if (!signal?.aborted) {
        setCatalog(result);
        setStatus(result.status || null);
        setLoading(false);
      }
    } catch (requestError) {
      if (!signal?.aborted) {
        setError(requestError.message);
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- setState is called inside async callback, not synchronously
    refresh(controller.signal);
    const timer = window.setInterval(() => refresh(controller.signal), 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh]);

  const runScenario = async () => {
    setError(null);
    try {
      const result = await startScenario(scenario, { duration_seconds: duration, seed });
      setStatus(result.status || result);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const stop = async () => {
    setError(null);
    try {
      setStatus(await stopScenario());
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const running = ["starting", "running", "stopping"].includes(status?.state);
  const definitions = catalog?.scenarios || [];

  return (
    <div className="compare-page">
      <header className="compare-page__header">
        <div className="compare-page__title-section">
          <h1>Network Experience Comparison</h1>
          <p className="compare-page__subtitle">Run a supported Scenario Lab workload. Comparison metrics appear only when a verified experiment result is available.</p>
        </div>
        <div className="compare-page__meta">
          <dl className="compare-page__meta-grid">
            <div><dt>Source</dt><dd><StatusBadges.Simulated size="sm" /></dd></div>
            <div><dt>Scenario state</dt><dd><StatusBadge variant={running ? "warning" : "unknown"} size="sm">{status?.state || "UNAVAILABLE"}</StatusBadge></dd></div>
            <div><dt>Run ID</dt><dd>{status?.run_id || "Unavailable"}</dd></div>
            <div><dt>Remaining</dt><dd>{status?.remaining_seconds == null ? "Unavailable" : `${status.remaining_seconds}s`}</dd></div>
          </dl>
        </div>
      </header>

      <section className="compare-page__section compare-page__controls">
        <h2>Scenario Lab</h2>
        <p className="compare-page__section-description">This control invokes the real bounded Scenario Lab API. It does not claim to be a baseline-versus-optimized experiment.</p>
        <div className="compare-page__controls-grid">
          <div className="compare-page__control-group">
            <label htmlFor="compare-scenario">Scenario<select id="compare-scenario" value={scenario} onChange={(event) => setScenario(event.target.value)} disabled={running}>
              {definitions.length ? definitions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>) : <option value="call_vs_download">Unavailable</option>}
            </select></label>
            <label htmlFor="compare-duration">Duration (seconds)<input id="compare-duration" type="number" min="5" max="120" value={duration} onChange={(event) => setDuration(Number(event.target.value))} disabled={running} /></label>
            <label htmlFor="compare-seed">Seed<input id="compare-seed" type="number" min="0" value={seed} onChange={(event) => setSeed(Number(event.target.value))} disabled={running} /></label>
          </div>
          <div className="compare-page__control-actions"><div className="compare-page__seed-indicator"><StatusBadges.Baseline /><span className="compare-page__vs">vs</span><StatusBadges.ExperienceBudget /><span>Comparison result unavailable until a paired experiment API is implemented.</span></div><div className="compare-page__buttons">{running ? <button className="btn btn--secondary" onClick={stop}>Stop Scenario</button> : <button className="btn btn--primary" onClick={runScenario} disabled={loading || !definitions.length}>Start Scenario</button>}</div></div>
        </div>
        {error && <div className="compare-page__error" role="alert">{error}</div>}
      </section>

      <UnavailableSection title="Metric comparison" text="No verified baseline and Experience Budget result set is available from the current backend contract." />
      <UnavailableSection title="Time-series comparison" text="Charts are intentionally withheld until real paired observations are returned. No fabricated points are rendered." />
      <UnavailableSection title="Household usage tree" text="Anonymous client observations are available on Live Control when the backend returns them. Physical household identities are not available." />
      <UnavailableSection title="Conclusion" text="Statistical improvement, fairness, starvation, and trade-offs cannot be concluded without paired repeated-trial results." />
    </div>
  );
}

function UnavailableSection({ title, text }) {
  return <section className="compare-page__section"><h2>{title}</h2><div className="compare-page__error" role="status"><StatusBadge variant="unknown" size="sm">UNAVAILABLE</StatusBadge><span>{text}</span></div></section>;
}

export default ComparePage;

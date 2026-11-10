import { useEffect, useRef, useState } from "react";
import { getScenarioCatalog, startScenario, stopScenario } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./ComparePage.css";

export function ComparePage() {
  const [catalog, setCatalog] = useState(null);
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
      try {
        const result = await getScenarioCatalog({ signal });
        if (!signal.aborted) {
          setCatalog(result);
          setStatus(result.status || null);
          setScenario((current) =>
            result.scenarios.some((item) => item.id === current)
              ? current
              : result.scenarios[0]?.id || "",
          );
          setCatalogError(null);
          setLoading(false);
        }
      } catch (requestError) {
        if (!signal.aborted) {
          setCatalogError(requestError.message);
          setLoading(false);
        }
      } finally {
        if (!disposed && !signal.aborted) {
          timer = window.setTimeout(poll, 5000);
        }
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

  return (
    <div className="compare-page">
      <header className="compare-page__header">
        <div className="compare-page__title-section">
          <h1>Network Experience Comparison</h1>
          <p className="compare-page__subtitle">Run a supported Scenario Lab workload. Comparison metrics appear only when a verified experiment result is available.</p>
        </div>
        <div className="compare-page__meta">
          <dl className="compare-page__meta-grid">
            <div><dt>Source</dt><dd><StatusBadge variant={catalog ? "simulated" : "unknown"} size="sm">{catalog ? "SIMULATED LAB" : "UNAVAILABLE"}</StatusBadge></dd></div>
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
            <label htmlFor="compare-scenario">Scenario<select id="compare-scenario" value={scenario} onChange={(event) => setScenario(event.target.value)} disabled={running || actionPending}>
              {definitions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select></label>
            <label htmlFor="compare-duration">Duration (seconds)<input id="compare-duration" type="number" min="5" max="120" value={duration} onChange={(event) => setDuration(Number(event.target.value))} disabled={running || actionPending} /></label>
            <label htmlFor="compare-seed">Seed<input id="compare-seed" type="number" min="0" max="2147483647" value={seed} onChange={(event) => setSeed(Number(event.target.value))} disabled={running || actionPending} /></label>
          </div>
          <div className="compare-page__control-actions"><div className="compare-page__seed-indicator"><span>Comparison result unavailable until a paired experiment API is implemented.</span></div><div className="compare-page__buttons">{running ? <button className="btn btn--secondary" onClick={stop} disabled={actionPending}>{actionPending ? "Stopping…" : "Stop Scenario"}</button> : <button className="btn btn--primary" onClick={runScenario} disabled={loading || actionPending || !scenario || !definitions.length}>{actionPending ? "Starting…" : "Start Scenario"}</button>}</div></div>
        </div>
        {catalogError && <div className="compare-page__error" role="alert">Scenario catalog unavailable: {catalogError}</div>}
        {actionError && <div className="compare-page__error" role="alert">{actionError}</div>}
      </section>

      <UnavailableSection title="Metric comparison" text="No verified baseline and Experience Budget result set is available from the current backend contract." />
      <UnavailableSection title="Time-series comparison" text="Charts are intentionally withheld until real paired observations are returned. No fabricated points are rendered." />
      <UnavailableSection title="Household usage tree" text="Anonymous client observations are available on Live Control when the backend returns them. Physical household identities are not available." />
      <UnavailableSection title="Conclusion" text="Statistical improvement, fairness, starvation, and trade-offs cannot be concluded without paired repeated-trial results." />
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

function UnavailableSection({ title, text }) {
  return <section className="compare-page__section"><h2>{title}</h2><div className="compare-page__error" role="status"><StatusBadge variant="unknown" size="sm">UNAVAILABLE</StatusBadge><span>{text}</span></div></section>;
}

export default ComparePage;

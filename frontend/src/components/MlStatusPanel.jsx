import { useEffect, useState } from "react";
import {
  getClassifierStatus,
  getForecastCurrent,
} from "../api/client";
import { StatusBadge } from "./ui/StatusBadge";
import "./MlStatusPanel.css";

const SOURCE_VARIANT = {
  model: "success",
  persistence_fallback: "warning",
  unavailable: "unknown",
};

/**
 * MlStatusPanel - live capacity forecast, Kalman capacity estimate and
 * classifier status. Results are lab-only proxies and labelled preliminary.
 * Unavailable models show "model unavailable"; values are never invented.
 */
export function MlStatusPanel() {
  const [forecast, setForecast] = useState(null);
  const [classifier, setClassifier] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let disposed = false;
    let controller;
    let timer;

    const poll = async () => {
      controller = new AbortController();
      const { signal } = controller;
      const [fc, cl] = await Promise.allSettled([
        getForecastCurrent({ signal }),
        getClassifierStatus({ signal }),
      ]);
      if (disposed || signal.aborted) return;
      if (fc.status === "fulfilled") setForecast(fc.value);
      if (cl.status === "fulfilled") setClassifier(cl.value);
      setError(
        fc.status === "rejected" && cl.status === "rejected"
          ? "ML status reconnecting…"
          : null,
      );
      if (!disposed) timer = window.setTimeout(poll, 5000);
    };

    poll();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, []);

  const horizons = forecast?.horizons || [];
  const capacity = forecast?.capacity_mbps;
  const uncertainty = forecast?.capacity_uncertainty_mbps;

  return (
    <section className="ml-status-panel">
      <header className="ml-status-panel__header">
        <h2>ML Models — Live Status</h2>
        <StatusBadge variant="simulated" size="sm">
          PRELIMINARY · LAB-ONLY
        </StatusBadge>
      </header>
      <p className="ml-status-panel__note">
        Forecasts and capacity are lab-derived proxies. Classifier metrics are
        held-out, run-level. Scripted-lab results do not prove real-ISP
        performance. {error && <span className="ml-status-panel__error">{error}</span>}
      </p>

      <div className="ml-status-panel__grid">
        <div className="ml-status-panel__card">
          <h3>Capacity estimate (Kalman)</h3>
          {capacity == null ? (
            <p className="ml-status-panel__unavailable">no data yet</p>
          ) : (
            <>
              <div className="ml-status-panel__capacity">
                <span className="ml-status-panel__capacity-value">
                  {capacity.toFixed(1)} Mbps
                </span>
                {uncertainty != null && (
                  <span className="ml-status-panel__capacity-band">
                    ± {uncertainty.toFixed(1)}
                  </span>
                )}
              </div>
              {uncertainty != null && (
                <div
                  className="ml-status-panel__capacity-bar"
                  aria-label={`capacity ${capacity.toFixed(1)} plus minus ${uncertainty.toFixed(1)} Mbps`}
                >
                  <div
                    className="ml-status-panel__capacity-fill"
                    style={{ width: `${Math.min(100, (capacity / 100) * 100)}%` }}
                  />
                </div>
              )}
            </>
          )}
          <span className="ml-status-panel__meta">
            {forecast?.history_samples ?? 0} history samples · model{" "}
            {forecast?.model_available ? "available" : "unavailable"}
          </span>
        </div>

        <div className="ml-status-panel__card">
          <h3>Capacity forecast</h3>
          {horizons.length === 0 ? (
            <p className="ml-status-panel__unavailable">model unavailable</p>
          ) : (
            <table className="ml-status-panel__table">
              <thead>
                <tr>
                  <th>Horizon</th>
                  <th>Forecast</th>
                  <th>Persistence</th>
                  <th>Source</th>
                  <th>Conf.</th>
                </tr>
              </thead>
              <tbody>
                {horizons.map((h) => (
                  <tr key={h.horizon_seconds}>
                    <td>{h.horizon_seconds}s</td>
                    <td>{h.forecast_mbps == null ? "—" : `${h.forecast_mbps.toFixed(1)}`}</td>
                    <td>{h.persistence_mbps == null ? "—" : `${h.persistence_mbps.toFixed(1)}`}</td>
                    <td>
                      <StatusBadge variant={SOURCE_VARIANT[h.source] || "unknown"} size="sm">
                        {h.source.replace("_fallback", " fallback")}
                      </StatusBadge>
                    </td>
                    <td>{h.confidence == null ? "—" : `${(h.confidence * 100).toFixed(0)}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="ml-status-panel__card">
          <h3>Traffic classifier</h3>
          {classifier == null ? (
            <p className="ml-status-panel__unavailable">model unavailable</p>
          ) : (
            <>
              <StatusBadge variant={classifier.available ? "success" : "unknown"} size="sm">
                {classifier.available ? "SERVING" : "UNAVAILABLE"}
              </StatusBadge>
              <dl className="ml-status-panel__metrics">
                <div>
                  <dt>Held-out F1</dt>
                  <dd>{classifier.held_out_f1 == null ? "—" : classifier.held_out_f1.toFixed(3)}</dd>
                </div>
                <div>
                  <dt>Baseline F1</dt>
                  <dd>{classifier.baseline_f1 == null ? "—" : classifier.baseline_f1.toFixed(3)}</dd>
                </div>
                <div>
                  <dt>Threshold</dt>
                  <dd>{(classifier.confidence_threshold * 100).toFixed(0)}%</dd>
                </div>
              </dl>
              <p className="ml-status-panel__reason">
                {classifier.last_fallback_reason || "no fallback"}
              </p>
              <p className="ml-status-panel__training-note">{classifier.training_note}</p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

export default MlStatusPanel;

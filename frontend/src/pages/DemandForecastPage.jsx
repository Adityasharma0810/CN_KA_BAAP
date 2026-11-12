import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getForecast } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import "./DemandForecastPage.css";

const HORIZONS = [5, 10, 30, 60];

/**
 * Demand Forecast - capacity forecast from real historical telemetry.
 */
export function DemandForecastPage() {
  const [horizon, setHorizon] = useState(30);
  const [forecast, setForecast] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const res = await getForecast("gw-local", horizon);
        if (disposed) return;
        setForecast(res);
      } catch {
        setForecast(null);
      }
    };
    load();
    return () => {
      disposed = true;
    };
  }, [horizon]);

  return (
    <div className="forecast-page">
      <header className="page-header">
        <h1>Demand Forecast</h1>
        <p className="subtitle">
          Capacity forecast from real historical telemetry. Forecasts only
          influence automatic policies when they pass validation and meet
          confidence thresholds.
        </p>
      </header>

      <div className="horizon-selector">
        {HORIZONS.map((h) => (
          <button
            key={h}
            className={`h-btn ${horizon === h ? "h-btn--active" : ""}`}
            onClick={() => setHorizon(h)}
          >
            {h}s
          </button>
        ))}
      </div>

      {!forecast ? (
        <EmptyState
          title="No forecast available"
          message="Historical telemetry is required before a forecast can be produced."
          action={() => navigate("/gateway-setup")}
          actionLabel="Set up a gateway"
        />
      ) : forecast.method === "unavailable" ? (
        <div className="forecast-unavailable">
          <StatusBadge variant="unknown" size="sm" />
          <span>
            Insufficient history for a {horizon}s forecast. Collect more
            real telemetry.
          </span>
        </div>
      ) : (
        <div className="forecast-card">
          <div className="forecast__result">
            <span className="forecast__label">Forecast ({forecast.method})</span>
            <span className="forecast__value">
              {forecast.forecast_mbps == null ? "—" : forecast.forecast_mbps} Mbps
            </span>
          </div>
          {forecast.confidence_interval && forecast.confidence_interval[0] != null && (
            <div className="forecast__ci">
              Confidence interval:
              {forecast.confidence_interval[0]} – {forecast.confidence_interval[1]} Mbps
            </div>
          )}
          <div className="forecast__computed">
            Computed {new Date(forecast.computed_at).toLocaleTimeString()}
          </div>
        </div>
      )}

      <div className="forecast-note">
        <p>
          ML forecasting only influences automatic policies after validation.
          Otherwise the reactive controller is used. Forecasting does not
          predict unobservable ISP events.
        </p>
      </div>
    </div>
  );
}

export default DemandForecastPage;

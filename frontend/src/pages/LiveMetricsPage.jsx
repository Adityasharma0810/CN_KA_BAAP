import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { getObservationHistory } from "../api/client";
import { StatusBadge } from "../components/ui/StatusBadge";
import "./LiveMetricsPage.css";

const METRICS = [
  { key: "download_mbps", label: "Download (Mbps)", color: "#587FA6", unit: " Mbps" },
  { key: "upload_mbps", label: "Upload (Mbps)", color: "#39765E", unit: " Mbps" },
  { key: "rtt_ms", label: "RTT (ms)", color: "#A97627", unit: " ms" },
  { key: "packet_loss_percent", label: "Packet loss (%)", color: "#A64D4D", unit: "%" },
];

/**
 * Live Metrics - real-time graphs from actual gateway telemetry.
 */
export function LiveMetricsPage() {
  const [metric, setMetric] = useState(METRICS[0]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const res = await getObservationHistory({
          source: "linux_gateway",
          scope: "aggregate_gateway",
          limit: 60,
        });
        if (disposed) return;
        setHistory(res.observations ?? []);
        const latest = (res.observations ?? [])[0];
        setStale(
          !!latest &&
          Date.now() - new Date(latest.metadata.observed_at).getTime() >
            300000,
        );
      } catch {
        setHistory([]);
        setStale(false);
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    load();
    return () => {
      disposed = true;
    };
  }, []);

  const latest = history[0];
  const isAggregate =
    latest?.metadata?.scope === "aggregate_gateway";

  return (
    <div className="live-metrics-page">
      <header className="page-header">
        <h1>Live Metrics</h1>
        <p className="subtitle">
          Real-time graphs from actual gateway telemetry. Historical range:
          last 60 samples.
        </p>
      </header>

      {!isAggregate && !loading ? (
        <div className="metrics-empty">
          <StatusBadge variant="unknown" size="sm" />
          <span>No aggregate gateway telemetry available.</span>
        </div>
      ) : null}

      <div className="chart-selector">
        {METRICS.map((m) => (
          <button
            key={m.key}
            className={`metric-btn ${metric.key === m.key ? "metric-btn--active" : ""}`}
            onClick={() => setMetric(m)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="chart-card">
        <div className="chart-card__header">
          <h2>{metric.label}</h2>
          <div className="chart-card__meta">
            <span className="freshness">
              {stale ? "Stale" : history.length ? "Live" : "—"}
            </span>
            <span className="source">
              {latest?.metadata?.source || "—"} ·
              {latest?.metadata?.environment || "—"}
            </span>
            <span className="quality">
              {latest?.metadata?.quality || "—"}
            </span>
          </div>
        </div>
        <div className="chart-wrapper">
          {loading ? (
            <div className="chart-placeholder">Loading…</div>
          ) : history.length === 0 ? (
            <div className="chart-placeholder">No data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={[...history].reverse()}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="metadata.observed_at" tick={10} />
                <YAxis />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey={metric.key}
                  stroke={metric.color}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
        {latest && !stale && (
          <div className="latest-value">
            Latest: {Number(latest[metric.key]).toFixed(2)}{metric.unit}
          </div>
        )}
        {stale && (
          <div className="stale-banner">
            Data is stale — no recent observation from the gateway.
          </div>
        )}
      </div>
    </div>
  );
}

export default LiveMetricsPage;

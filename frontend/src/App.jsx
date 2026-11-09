import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  collectHostMeasurement,
  collectHotspotMeasurement,
} from "./api/client";
import NetworkTopology from "./components/NetworkTopology";
import useProductData, { HISTORY_LIMIT } from "./hooks/useProductData";
import "./App.css";

const SOURCES = [
  ["application", "Application"],
  ["windows_host", "Windows host"],
  ["hotspot", "Hotspot"],
  ["linux_lab", "Linux lab"],
];

const METRICS = [
  ["download_mbps", "Download", "Mbps", 3],
  ["upload_mbps", "Upload", "Mbps", 3],
  ["rtt_ms", "RTT", "ms", 1],
  ["packet_loss_percent", "Packet loss", "%", 1],
  ["rtt_variation_ms", "RTT variation", "ms", 1],
  ["download_bytes", "Downloaded", "bytes", 0],
  ["upload_bytes", "Uploaded", "bytes", 0],
];

function displayTime(value) {
  if (!value) return "Never observed";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}

function stateText(state) {
  return state === "online" ? "recently measured" : state || "unknown";
}

function formatValue(value, unit, digits = 2) {
  if (value === null || value === undefined) return "No data";
  const formatted =
    unit === "bytes"
      ? Number(value).toLocaleString()
      : Number(value).toFixed(digits);
  return `${formatted} ${unit}`;
}

function Provenance({ metadata }) {
  if (!metadata) return <span className="provenance">Provenance unavailable</span>;
  return (
    <span
      className="provenance"
      title={`Source: ${metadata.source}; scope: ${metadata.scope}; environment: ${metadata.environment}; quality: ${metadata.quality}`}
    >
      {metadata.source} · {metadata.scope} · {metadata.environment} ·{" "}
      {metadata.quality}
      {metadata.stale ? " · stale" : ""}
    </span>
  );
}

function PanelFeedback({ result, title }) {
  if (result?.loading && !result.data) {
    return <p className="panel-feedback">Loading {title.toLowerCase()}…</p>;
  }
  if (result?.error && !result.data) {
    return <p className="panel-feedback error-text">{result.error.message}</p>;
  }
  if (result?.error && result.data) {
    return (
      <p className="panel-feedback warning-text">
        Refresh failed: {result.error.message} Last-known data is shown as stale.
      </p>
    );
  }
  return null;
}

function MeasurementCard({ title, observation, aggregate = false }) {
  const metadata = observation?.metadata;
  return (
    <article className="measurement-card">
      <div className="measurement-heading">
        <h3>{title}</h3>
        {aggregate && <span className="aggregate-badge">Aggregate only</span>}
      </div>
      {aggregate && (
        <p className="aggregate-note">
          This measurement describes a group or host, not individual devices.
        </p>
      )}
      {!observation ? (
        <p className="empty-copy">No stored observation available.</p>
      ) : (
        <>
          <div className="measurement-grid">
            {METRICS.map(([key, label, unit, digits]) => (
              <div className="measurement-value" key={key}>
                <span>{label}</span>
                <strong>{formatValue(observation[key], unit, digits)}</strong>
              </div>
            ))}
          </div>
          <div className="measurement-meta">
            <span>Observed {displayTime(metadata?.observed_at)}</span>
            <Provenance metadata={metadata} />
          </div>
        </>
      )}
    </article>
  );
}

function StatusBar({ result }) {
  const gateway = result?.data;
  const causedBy = gateway
    ? SOURCES.filter(([key]) => gateway[key]?.state !== "online")
        .map(([, label]) => label)
        .join(", ")
    : "";

  return (
    <section className="status-panel" aria-label="Gateway status">
      <PanelFeedback result={result} title="Gateway status" />
      {gateway ? (
        <>
          <div className="overall-status">
            <div>
              <span className="eyebrow">Overall gateway status</span>
              <strong className={`state-label state-${gateway.status}`}>
                {gateway.status}
              </strong>
              {(gateway.status === "degraded" ||
                gateway.status === "unavailable") && (
                <p className="status-cause">
                  Needs attention: {causedBy || "source status unavailable"}
                </p>
              )}
            </div>
            <span className="observed-time">
              Checked {displayTime(gateway.observed_at)}
            </span>
          </div>
          <div className="source-statuses">
            {SOURCES.map(([key, label]) => {
              const item = gateway[key];
              return (
                <div className="source-status" key={key}>
                  <span>{label}</span>
                  <strong className={`state-label state-${item?.state || "unknown"}`}>
                    {stateText(item?.state)}
                  </strong>
                  <small>Last observed: {displayTime(item?.last_observed_at)}</small>
                  <small>Quality: {item?.data_quality || "unknown"}</small>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        !result?.loading && (
          <p className="empty-copy">Gateway status is not available.</p>
        )
      )}
    </section>
  );
}

function ApiHealthPanel({ healthResult, collectorResult }) {
  const components = healthResult?.data?.components;
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>API and collector health</h2>
          <p>Health checks are separate from measurement collection.</p>
        </div>
      </div>
      <PanelFeedback result={healthResult} title="API health" />
      <PanelFeedback result={collectorResult} title="Collector health" />
      {components ? (
        <div className="health-grid">
          {Object.entries(components).map(([name, component]) => (
            <div className="health-item" key={name}>
              <span>{name.replaceAll("_", " ")}</span>
              <strong className={`state-label state-${component.status}`}>
                {component.status}
              </strong>
              <small>Last success: {displayTime(component.last_success_at)}</small>
            </div>
          ))}
        </div>
      ) : (
        !healthResult?.loading &&
        !healthResult?.error && (
          <p className="empty-copy">No API health data available.</p>
        )
      )}
      {collectorResult?.data?.collectors?.length > 0 && (
        <div className="collector-list">
          <h3>Collectors</h3>
          {collectorResult.data.collectors.map((collector) => (
            <div className="collector-row" key={collector.collector}>
              <span>{collector.collector.replaceAll("_", " ")}</span>
              <strong className={`state-label state-${collector.status}`}>
                {collector.status}
              </strong>
              <small>Last success: {displayTime(collector.last_success_at)}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ClientMeasurements({ nodes, observations, result, topologyResult }) {
  const clients = nodes.filter((node) => node.kind === "client");
  const registryUnavailable = topologyResult?.data?.sources?.some(
    (source) =>
      source.source === "anonymous_registry" &&
      source.state === "unavailable",
  );
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Anonymous lab clients</h2>
          <p>Client names and measurements are limited to anonymous lab data.</p>
        </div>
      </div>
      <PanelFeedback result={result} title="Current observations" />
      {clients.length === 0 ? (
        !result?.loading && (
          <p className="empty-copy">
            {registryUnavailable
              ? "Anonymous client registry is unavailable."
              : "No anonymous clients were returned by the topology API."}
          </p>
        )
      ) : (
        <div className="client-list">
          {clients.map((client) => {
            const observation = observations.find(
              (item) =>
                item.metadata?.client_id &&
                item.metadata.client_id === client.client_id,
            );
            return (
              <article className="client-card" key={client.node_id}>
                <div className="client-title">
                  <h3>{client.label}</h3>
                  <span className={`state-label state-${client.state}`}>
                    {stateText(client.state)}
                  </span>
                </div>
                <code className="client-id">{client.client_id}</code>
                <div className="measurement-grid">
                  {METRICS.slice(0, 5).map(([key, label, unit, digits]) => (
                    <div className="measurement-value" key={key}>
                      <span>{label}</span>
                      <strong>{formatValue(observation?.[key], unit, digits)}</strong>
                    </div>
                  ))}
                </div>
                {observation ? (
                  <div className="measurement-meta">
                    <span>Observed {displayTime(observation.metadata.observed_at)}</span>
                    <Provenance metadata={observation.metadata} />
                  </div>
                ) : (
                  <p className="empty-copy">No current client observation.</p>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function observationRows(response) {
  return (response?.observations || []).map((item) => item.observation);
}

function HistoryTooltip({ active, payload, label }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {METRICS.slice(0, 5).map(([key, name, unit, digits]) => (
        <div key={key}>
          {name}: {formatValue(row[key], unit, digits)}
        </div>
      ))}
      <Provenance metadata={row.metadata} />
    </div>
  );
}

function HistoryPanel({
  result,
  clientResult,
  clients,
  selectedClientId,
  onClientChange,
  range,
  onRangeChange,
}) {
  const historyResult =
    result?.filterKey === range
      ? result
      : { loading: true, data: null, error: null };
  const clientFilterKey = `${selectedClientId}|${range}`;
  const selectedClientResult =
    clientResult?.filterKey === clientFilterKey
      ? clientResult
      : { loading: true, data: null, error: null };
  const aggregate = observationRows(historyResult.data);
  const clientHistory = observationRows(selectedClientResult.data);
  const chartRows = useMemo(
    () =>
      (selectedClientId ? clientHistory : aggregate)
        .slice()
        .reverse()
        .map((observation) => ({
          ...observation,
          time: new Date(observation.metadata.observed_at).toLocaleString(),
        })),
    [aggregate, clientHistory, selectedClientId],
  );
  const activeResult = selectedClientId ? selectedClientResult : historyResult;
  const page = selectedClientId
    ? selectedClientResult.data
    : historyResult.data;

  return (
    <section className="panel">
      <div className="section-heading history-heading">
        <div>
          <h2>Observation history</h2>
          <p>Charts preserve missing values; null is never shown as zero.</p>
        </div>
        <div className="history-controls">
          <label>
            Time range
            <select value={range} onChange={(event) => onRangeChange(event.target.value)}>
              <option value="1h">Last hour</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select>
          </label>
          <label>
            Client
            <select
              value={selectedClientId}
              onChange={(event) => onClientChange(event.target.value)}
            >
              <option value="">Aggregate history</option>
              {clients.map((client) => (
                <option key={client.client_id} value={client.client_id}>
                  {client.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <PanelFeedback result={activeResult} title="History" />
      {chartRows.length === 0 ? (
        !activeResult?.loading && (
          <p className="empty-copy">
            No history is available for this range and selection.
          </p>
        )
      ) : (
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={chartRows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" minTickGap={30} />
            <YAxis />
            <Tooltip content={<HistoryTooltip />} />
            <Line
              type="monotone"
              dataKey="download_mbps"
              stroke="#2563eb"
              connectNulls={false}
              name="Download Mbps"
            />
            <Line
              type="monotone"
              dataKey="upload_mbps"
              stroke="#16a34a"
              connectNulls={false}
              name="Upload Mbps"
            />
            <Line
              type="monotone"
              dataKey="rtt_ms"
              stroke="#9333ea"
              connectNulls={false}
              name="RTT ms"
            />
          </LineChart>
        </ResponsiveContainer>
      )}
      {page?.has_more && (
        <p className="cap-notice">
          Showing the newest {HISTORY_LIMIT} observations in this range. Narrow
          the time range to inspect fewer records.
        </p>
      )}
      {chartRows.length > 0 && (
        <p className="chart-provenance">
          Source, scope, environment, and quality are available in each chart
          tooltip.
        </p>
      )}
    </section>
  );
}

function App() {
  const [historyRangeValue, setHistoryRangeValue] = useState("24h");
  const [selectedClientId, setSelectedClientId] = useState("");
  const [collecting, setCollecting] = useState(false);
  const [collectionError, setCollectionError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const results = useProductData({ historyRangeValue, selectedClientId, refreshToken });
  const topology = results.topology?.data;
  const nodes = topology?.nodes || [];
  const clientNodes = nodes.filter((node) => node.kind === "client");
  const currentObservations = observationRows(results.current?.data);
  const aggregateObservations = currentObservations.filter(
    (observation) => observation.metadata?.scope !== "client",
  );
  const clientObservations = currentObservations.filter(
    (observation) => observation.metadata?.scope === "client",
  );
  const networkUnavailable = Object.values(results).some(
    (result) =>
      result?.error &&
      (result.error.kind === "network" || result.error.kind === "timeout"),
  );
  const hostObservation = aggregateObservations.find(
    (observation) => observation.metadata?.source === "windows_host",
  );
  const hotspotObservation = aggregateObservations.find(
    (observation) => observation.metadata?.source === "windows_hotspot",
  );
  const linuxGatewayObservation = aggregateObservations.find(
    (observation) => observation.metadata?.source === "linux_gateway",
  );

  const sourceResults = useMemo(
    () => Object.values(results),
    [results],
  );

  const collectNow = async () => {
    if (collecting) return;
    setCollecting(true);
    setCollectionError("");
    const outcomes = await Promise.allSettled([
      collectHostMeasurement(),
      collectHotspotMeasurement(),
    ]);
    setRefreshToken((token) => token + 1);
    const failures = outcomes.filter((outcome) => outcome.status === "rejected");
    if (failures.length > 0) {
      setCollectionError(
        `${failures.length} collection request${failures.length === 1 ? "" : "s"} failed.`,
      );
    }
    setCollecting(false);
  };

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Experience Budget</h1>
          <p>Privacy-preserving, evidence-based network monitoring</p>
        </div>
        <button
          className="collect-button"
          onClick={collectNow}
          disabled={collecting}
        >
          {collecting ? "Collecting…" : "Collect now"}
        </button>
      </header>

      {networkUnavailable && (
        <div className="backend-banner" role="status">
          Backend unreachable. Last-known results are retained and marked stale
          where available.
        </div>
      )}
      {collectionError && (
        <div className="backend-banner error-banner" role="alert">
          {collectionError}
        </div>
      )}

      <StatusBar result={results.gateway} />

      <ApiHealthPanel
        healthResult={results.health}
        collectorResult={results.collectors}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Aggregate measurements</h2>
            <p>
              Stored canonical observations. Missing values are shown as “No
              data.”
            </p>
          </div>
        </div>
        <PanelFeedback result={results.current} title="Current observations" />
        <div className="measurement-cards">
          <MeasurementCard
            title="Windows host"
            observation={hostObservation}
            aggregate
          />
          <MeasurementCard
            title="Hotspot"
            observation={hotspotObservation}
            aggregate
          />
          <MeasurementCard
            title="Linux gateway"
            observation={linuxGatewayObservation}
            aggregate
          />
        </div>
        {!results.current?.loading &&
          !results.current?.error &&
          aggregateObservations.length === 0 && (
            <p className="empty-copy">No aggregate observations are stored.</p>
          )}
      </section>

      <ClientMeasurements
        nodes={nodes}
        observations={clientObservations}
        result={results.current}
        topologyResult={results.topology}
      />

      <NetworkTopology result={results.topology} />

      <HistoryPanel
        result={results.history}
        clientResult={results.clientHistory}
        clients={clientNodes}
        selectedClientId={selectedClientId}
        onClientChange={setSelectedClientId}
        range={historyRangeValue}
        onRangeChange={setHistoryRangeValue}
      />

      <footer className="dashboard-footer">
        <p>
          Online means recently measured, not connected. Windows host and
          hotspot values are aggregates; no per-device attribution is inferred.
        </p>
        <p>
          Refreshing reads product APIs only. Collection runs only after an
          explicit “Collect now” action.
        </p>
        <span className="sr-only">
          {sourceResults.filter((result) => result?.stale).length} API responses
          are stale.
        </span>
      </footer>
    </main>
  );
}

export default App;

import { useCallback, useEffect, useRef, useState } from "react";
import NetworkTopology from "./components/NetworkTopology";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";


function App() {
  const [hotspotData, setHotspotData] = useState([]);
  const [labClients, setLabClients] = useState([]);
  const [autoMonitoring, setAutoMonitoring] = useState(false);
  const inFlightRef = useRef(false);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [collecting, setCollecting] = useState(false);

  const fetchHistory = useCallback(async () => {
    try {
      const [upstreamResponse, hotspotResponse, labResponse] = await Promise.all([
        fetch(`${API_BASE}/api/v1/monitoring/history?limit=50`),
        fetch(`${API_BASE}/api/v1/monitoring/hotspot/history?limit=50`),
        fetch(`${API_BASE}/api/v1/monitoring/lab/clients`),
      ]);

      if (!upstreamResponse.ok || !hotspotResponse.ok || !labResponse.ok) {
        throw new Error("Could not load network history.");
      }

      const upstreamResult = await upstreamResponse.json();
      const hotspotResult = await hotspotResponse.json();
      const labResult = await labResponse.json();

      const upstreamSamples = upstreamResult.samples
        .slice()
        .reverse()
        .map((sample) => ({
          id: sample.id,
          time: new Date(sample.recorded_at).toLocaleTimeString(),
          download: sample.download_mbps ?? 0,
          upload: sample.upload_mbps ?? 0,
          rtt: sample.rtt_avg_ms ?? 0,
          jitter: sample.rtt_jitter_avg_ms ?? 0,
          packetLoss: sample.packet_loss_percent ?? 0,
          online:
            sample.internet_reachable === 1 ||
            sample.internet_reachable === true,
        }));

      const downstreamSamples = hotspotResult.samples
        .slice()
        .reverse()
        .map((sample) => ({
          id: sample.id,
          time: new Date(sample.recorded_at).toLocaleTimeString(),
          download: sample.download_mbps ?? 0,
          upload: sample.upload_mbps ?? 0,
        }));

      setData(upstreamSamples);
      setHotspotData(downstreamSamples);
      setLabClients(labResult.available ? labResult.clients : []);
      setError(null);

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);


  const collectMeasurement = useCallback(async () => {
    if (inFlightRef.current) return;

    inFlightRef.current = true;
    setCollecting(true);
    setError(null);

    try {
      // Collect laptop upstream measurements
      const upstreamResponse = await fetch(
        `${API_BASE}/api/v1/monitoring/collect`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            adapter: "Wi-Fi",
            sample_interval_seconds: 1,
            quality_target: "1.1.1.1",
            quality_count: 5,
          }),
        }
      );

      if (!upstreamResponse.ok) {
        throw new Error("Upstream collection failed.");
      }

      await upstreamResponse.json();

      // Collect downstream hotspot measurements
      const hotspotResponse = await fetch(
        `${API_BASE}/api/v1/monitoring/hotspot/collect`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            sample_interval_seconds: 1,
          }),
        }
      );

      if (!hotspotResponse.ok) {
        throw new Error("Hotspot collection failed.");
      }

      await hotspotResponse.json();

      // Refresh both datasets
      await fetchHistory();

    } catch (err) {
      setError(err.message);
    } finally {
      inFlightRef.current = false;
      setCollecting(false);
    }
  }, [fetchHistory]);


  // Initial dashboard load
  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const [upstreamResponse, hotspotResponse, labResponse] = await Promise.all([
          fetch(`${API_BASE}/api/v1/monitoring/history?limit=50`),
          fetch(`${API_BASE}/api/v1/monitoring/hotspot/history?limit=50`),
          fetch(`${API_BASE}/api/v1/monitoring/lab/clients`),
        ]);

        if (!upstreamResponse.ok || !hotspotResponse.ok || !labResponse.ok) {
          throw new Error("Could not load network history.");
        }

        const upstreamResult = await upstreamResponse.json();
        const hotspotResult = await hotspotResponse.json();
        const labResult = await labResponse.json();

        if (ignore) return;

        const upstreamSamples = upstreamResult.samples
          .slice()
          .reverse()
          .map((sample) => ({
            id: sample.id,
            time: new Date(sample.recorded_at).toLocaleTimeString(),
            download: sample.download_mbps ?? 0,
            upload: sample.upload_mbps ?? 0,
            rtt: sample.rtt_avg_ms ?? 0,
            jitter: sample.rtt_jitter_avg_ms ?? 0,
            packetLoss: sample.packet_loss_percent ?? 0,
            online:
              sample.internet_reachable === 1 ||
              sample.internet_reachable === true,
          }));

        const downstreamSamples = hotspotResult.samples
          .slice()
          .reverse()
          .map((sample) => ({
            id: sample.id,
            time: new Date(sample.recorded_at).toLocaleTimeString(),
            download: sample.download_mbps ?? 0,
            upload: sample.upload_mbps ?? 0,
          }));

        setData(upstreamSamples);
        setHotspotData(downstreamSamples);
        setLabClients(labResult.available ? labResult.clients : []);
        setError(null);
      } catch (err) {
        if (!ignore) setError(err.message);
      } finally {
        if (!ignore) setLoading(false);
      }
    };

    load();
    return () => {
      ignore = true;
    };
  }, []);

  // Automatic monitoring
  useEffect(() => {
    if (!autoMonitoring) return;

    // Collect immediately when automatic monitoring starts.
    const startTimer = window.setTimeout(() => {
      collectMeasurement();
    }, 0);

    // Collect again every 15 seconds.
    const intervalTimer = window.setInterval(() => {
      collectMeasurement();
    }, 15000);

    return () => {
      window.clearTimeout(startTimer);
      window.clearInterval(intervalTimer);
    };
  }, [autoMonitoring, collectMeasurement]);

  if (loading) {
    return (
      <div className="dashboard loading-screen">
        Loading network measurements...
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard loading-screen error-screen">
        <h2>Unable to load monitoring data</h2>
        <p>{error}</p>
        <button onClick={fetchHistory}>Try Again</button>
      </div>
    );
  }

  const latest = data[data.length - 1];

  return (
    <div className="dashboard">
      <header>
        <div>
          <h1>Experience Budget</h1>
          <p>Privacy-preserving network baseline monitoring</p>
        </div>

        <div className="header-actions">
          <button
            className={`auto-button ${autoMonitoring ? "active" : ""}`}
            onClick={() => setAutoMonitoring((current) => !current)}
          >
            {autoMonitoring ? "Stop Monitoring" : "Start Monitoring"}
          </button>

          <button
            className="collect-button"
            onClick={collectMeasurement}
            disabled={collecting}
          >
            {collecting ? "Collecting..." : "Collect Now"}
          </button>

          <div className={`status ${latest?.online ? "" : "offline"}`}>
            <span className="status-dot"></span>
            {latest?.online ? "ONLINE" : "NO DATA"}
          </div>
        </div>
      </header>
      <NetworkTopology
        upstream={data[data.length - 1]}
        downstream={hotspotData[hotspotData.length - 1]}
        labClients={labClients}
      />

      {data.length === 0 ? (
        <section className="chart-card empty-state">
          <h2>No measurements yet</h2>
          <p>
            Collect a network measurement from the FastAPI API first.
          </p>
        </section>
      ) : (
        <>
          <section className="metrics">
            <div className="card">
              <p>Download</p>
              <h2>{latest.download.toFixed(3)} Mbps</h2>
            </div>

            <div className="card">
              <p>Upload</p>
              <h2>{latest.upload.toFixed(3)} Mbps</h2>
            </div>

            <div className="card">
              <p>Average RTT</p>
              <h2>{latest.rtt.toFixed(1)} ms</h2>
            </div>

            <div className="card">
              <p>Packet Loss</p>
              <h2>{latest.packetLoss.toFixed(1)}%</h2>
            </div>
          </section>

          <section className="chart-card">
            <h2>Bandwidth History</h2>

            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="download"
                  stroke="#2563eb"
                  strokeWidth={3}
                  name="Download Mbps"
                />
                <Line
                  type="monotone"
                  dataKey="upload"
                  stroke="#16a34a"
                  strokeWidth={3}
                  name="Upload Mbps"
                />
              </LineChart>
            </ResponsiveContainer>
          </section>

          <section className="chart-card">
            <h2>Network Quality History</h2>

            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip />

                <Line
                  type="monotone"
                  dataKey="rtt"
                  stroke="#9333ea"
                  strokeWidth={3}
                  name="Average RTT (ms)"
                />

                <Line
                  type="monotone"
                  dataKey="jitter"
                  stroke="#ea580c"
                  strokeWidth={3}
                  name="RTT Variation (ms)"
                />
              </LineChart>
            </ResponsiveContainer>
          </section>
        </>
      )}

      <footer>
        <p>
          Scope: Local adapter aggregate monitoring only. No connected-device
          identities or private traffic data are collected.
        </p>
      </footer>
    </div>
  );
}

export default App;
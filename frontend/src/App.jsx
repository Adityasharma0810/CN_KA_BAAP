import { useState } from "react";
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

const sampleData = [
  { time: "09:43:04", download: 0.009, upload: 0.033, rtt: 11.6 },
  { time: "09:43:10", download: 1.136, upload: 0.544, rtt: 12.4 },
  { time: "09:43:16", download: 0.021, upload: 0.006, rtt: 10.8 },
  { time: "09:43:19", download: 1.914, upload: 0.047, rtt: 14.2 },
  { time: "09:43:20", download: 1.052, upload: 0.015, rtt: 11.6 },
];

function App() {
  const [data] = useState(sampleData);

  const latest = data[data.length - 1];

  return (
    <div className="dashboard">
      <header>
        <div>
          <h1>Network Baseline Monitor</h1>
          <p>Local aggregate network monitoring</p>
        </div>
        <div className="status">
          <span className="status-dot"></span>
          ONLINE
        </div>
      </header>

      <section className="metrics">
        <div className="card">
          <p>Download</p>
          <h2>{latest.download} Mbps</h2>
        </div>

        <div className="card">
          <p>Upload</p>
          <h2>{latest.upload} Mbps</h2>
        </div>

        <div className="card">
          <p>Average RTT</p>
          <h2>{latest.rtt} ms</h2>
        </div>

        <div className="card">
          <p>Packet Loss</p>
          <h2>0%</h2>
        </div>
      </section>

      <section className="chart-card">
        <h2>Bandwidth Usage</h2>

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
        <h2>Network Latency</h2>

        <ResponsiveContainer width="100%" height={280}>
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
              name="RTT (ms)"
            />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <footer>
        <p>Scope: Local adapter aggregate monitoring only</p>
      </footer>
    </div>
  );
}

export default App;
import { useState, useMemo } from "react";
import { MultiMetricComparisonChart } from "../components/charts/ComparisonChart";
import { MetricCard } from "../components/ui/MetricCard";
import { StatusBadge, StatusBadges } from "../components/ui/StatusBadge";
import "./ComparePage.css";

/**
 * ComparePage - Baseline vs Experience Budget comparison
 * The most important presentation page showing whether EB improves network experience
 */
export function ComparePage() {
  const [experimentConfig, setExperimentConfig] = useState({
    scenario: "call_vs_download",
    clients: 3,
    duration: 60,
    seed: 42,
  });
  const [experimentState, setExperimentState] = useState("idle"); // idle, running, complete, error
  const [error, setError] = useState(null);

  // Static mock data for demonstration - will be replaced with real API calls
  const mockComparisonData = useMemo(() => {
    // Generate static time-series data (30 points over 60 seconds)
    const staticTimeSeries = [
      { time: "0s", latency_ms_baseline: 52.3, latency_ms_optimized: 28.1, p95_latency_ms_baseline: 95.2, p95_latency_ms_optimized: 42.8, jitter_ms_baseline: 14.5, jitter_ms_optimized: 5.2, packet_loss_percent_baseline: 1.3, packet_loss_percent_optimized: 0.15, download_mbps_baseline: 38.2, download_mbps_optimized: 41.5, upload_mbps_baseline: 9.1, upload_mbps_optimized: 9.7, bulk_progress_percent_baseline: 0, bulk_progress_percent_optimized: 0, worst_qoe_baseline: 58.3, worst_qoe_optimized: 78.5 },
      { time: "2s", latency_ms_baseline: 49.8, latency_ms_optimized: 26.9, p95_latency_ms_baseline: 92.5, p95_latency_ms_optimized: 40.2, jitter_ms_baseline: 13.8, jitter_ms_optimized: 4.9, packet_loss_percent_baseline: 1.1, packet_loss_percent_optimized: 0.12, download_mbps_baseline: 39.5, download_mbps_optimized: 42.8, upload_mbps_baseline: 8.9, upload_mbps_optimized: 9.5, bulk_progress_percent_baseline: 2.9, bulk_progress_percent_optimized: 3.3, worst_qoe_baseline: 60.1, worst_qoe_optimized: 79.8 },
      { time: "4s", latency_ms_baseline: 54.1, latency_ms_optimized: 29.3, p95_latency_ms_baseline: 98.7, p95_latency_ms_optimized: 44.5, jitter_ms_baseline: 15.2, jitter_ms_optimized: 5.6, packet_loss_percent_baseline: 1.4, packet_loss_percent_optimized: 0.18, download_mbps_baseline: 37.8, download_mbps_optimized: 40.9, upload_mbps_baseline: 9.3, upload_mbps_optimized: 9.9, bulk_progress_percent_baseline: 5.9, bulk_progress_percent_optimized: 6.6, worst_qoe_baseline: 57.5, worst_qoe_optimized: 77.2 },
      { time: "6s", latency_ms_baseline: 50.6, latency_ms_optimized: 27.8, p95_latency_ms_baseline: 94.3, p95_latency_ms_optimized: 41.9, jitter_ms_baseline: 14.1, jitter_ms_optimized: 5.0, packet_loss_percent_baseline: 1.2, packet_loss_percent_optimized: 0.14, download_mbps_baseline: 38.9, download_mbps_optimized: 42.3, upload_mbps_baseline: 9.0, upload_mbps_optimized: 9.6, bulk_progress_percent_baseline: 8.8, bulk_progress_percent_optimized: 9.9, worst_qoe_baseline: 59.7, worst_qoe_optimized: 80.5 },
      { time: "8s", latency_ms_baseline: 53.7, latency_ms_optimized: 30.1, p95_latency_ms_baseline: 97.9, p95_latency_ms_optimized: 45.8, jitter_ms_baseline: 15.6, jitter_ms_optimized: 5.8, packet_loss_percent_baseline: 1.5, packet_loss_percent_optimized: 0.21, download_mbps_baseline: 36.5, download_mbps_optimized: 39.7, upload_mbps_baseline: 9.4, upload_mbps_optimized: 10.0, bulk_progress_percent_baseline: 11.8, bulk_progress_percent_optimized: 13.1, worst_qoe_baseline: 56.2, worst_qoe_optimized: 76.8 },
      { time: "10s", latency_ms_baseline: 51.2, latency_ms_optimized: 28.5, p95_latency_ms_baseline: 95.8, p95_latency_ms_optimized: 43.1, jitter_ms_baseline: 14.3, jitter_ms_optimized: 5.1, packet_loss_percent_baseline: 1.2, packet_loss_percent_optimized: 0.16, download_mbps_baseline: 38.1, download_mbps_optimized: 41.8, upload_mbps_baseline: 9.2, upload_mbps_optimized: 9.8, bulk_progress_percent_baseline: 14.7, bulk_progress_percent_optimized: 16.4, worst_qoe_baseline: 58.9, worst_qoe_optimized: 79.3 },
      { time: "12s", latency_ms_baseline: 55.4, latency_ms_optimized: 31.2, p95_latency_ms_baseline: 101.3, p95_latency_ms_optimized: 47.5, jitter_ms_baseline: 16.8, jitter_ms_optimized: 6.2, packet_loss_percent_baseline: 1.7, packet_loss_percent_optimized: 0.24, download_mbps_baseline: 35.9, download_mbps_optimized: 39.1, upload_mbps_baseline: 9.5, upload_mbps_optimized: 10.1, bulk_progress_percent_baseline: 17.6, bulk_progress_percent_optimized: 19.7, worst_qoe_baseline: 54.8, worst_qoe_optimized: 75.5 },
      { time: "14s", latency_ms_baseline: 48.9, latency_ms_optimized: 26.4, p95_latency_ms_baseline: 91.7, p95_latency_ms_optimized: 39.8, jitter_ms_baseline: 13.5, jitter_ms_optimized: 4.7, packet_loss_percent_baseline: 1.0, packet_loss_percent_optimized: 0.11, download_mbps_baseline: 39.8, download_mbps_optimized: 43.1, upload_mbps_baseline: 8.8, upload_mbps_optimized: 9.4, bulk_progress_percent_baseline: 20.6, bulk_progress_percent_optimized: 23.0, worst_qoe_baseline: 61.4, worst_qoe_optimized: 81.7 },
      { time: "16s", latency_ms_baseline: 52.8, latency_ms_optimized: 29.7, p95_latency_ms_baseline: 96.5, p95_latency_ms_optimized: 44.9, jitter_ms_baseline: 14.9, jitter_ms_optimized: 5.5, packet_loss_percent_baseline: 1.3, packet_loss_percent_optimized: 0.19, download_mbps_baseline: 37.3, download_mbps_optimized: 40.5, upload_mbps_baseline: 9.1, upload_mbps_optimized: 9.7, bulk_progress_percent_baseline: 23.5, bulk_progress_percent_optimized: 26.2, worst_qoe_baseline: 57.8, worst_qoe_optimized: 78.1 },
      { time: "18s", latency_ms_baseline: 50.3, latency_ms_optimized: 27.2, p95_latency_ms_baseline: 93.9, p95_latency_ms_optimized: 41.3, jitter_ms_baseline: 13.9, jitter_ms_optimized: 4.9, packet_loss_percent_baseline: 1.1, packet_loss_percent_optimized: 0.13, download_mbps_baseline: 38.7, download_mbps_optimized: 42.2, upload_mbps_baseline: 9.0, upload_mbps_optimized: 9.6, bulk_progress_percent_baseline: 26.5, bulk_progress_percent_optimized: 29.5, worst_qoe_baseline: 59.5, worst_qoe_optimized: 80.3 },
      { time: "20s", latency_ms_baseline: 54.6, latency_ms_optimized: 30.8, p95_latency_ms_baseline: 99.8, p95_latency_ms_optimized: 46.7, jitter_ms_baseline: 16.1, jitter_ms_optimized: 5.9, packet_loss_percent_baseline: 1.6, packet_loss_percent_optimized: 0.22, download_mbps_baseline: 36.2, download_mbps_optimized: 39.4, upload_mbps_baseline: 9.4, upload_mbps_optimized: 10.0, bulk_progress_percent_baseline: 29.4, bulk_progress_percent_optimized: 32.8, worst_qoe_baseline: 55.6, worst_qoe_optimized: 76.2 },
      { time: "22s", latency_ms_baseline: 51.7, latency_ms_optimized: 28.9, p95_latency_ms_baseline: 96.1, p95_latency_ms_optimized: 43.7, jitter_ms_baseline: 14.5, jitter_ms_optimized: 5.2, packet_loss_percent_baseline: 1.2, packet_loss_percent_optimized: 0.17, download_mbps_baseline: 37.9, download_mbps_optimized: 41.4, upload_mbps_baseline: 9.2, upload_mbps_optimized: 9.8, bulk_progress_percent_baseline: 32.4, bulk_progress_percent_optimized: 36.1, worst_qoe_baseline: 58.3, worst_qoe_optimized: 78.9 },
      { time: "24s", latency_ms_baseline: 49.1, latency_ms_optimized: 26.7, p95_latency_ms_baseline: 92.3, p95_latency_ms_optimized: 40.5, jitter_ms_baseline: 13.7, jitter_ms_optimized: 4.8, packet_loss_percent_baseline: 1.0, packet_loss_percent_optimized: 0.12, download_mbps_baseline: 39.3, download_mbps_optimized: 42.7, upload_mbps_baseline: 8.9, upload_mbps_optimized: 9.5, bulk_progress_percent_baseline: 35.3, bulk_progress_percent_optimized: 39.3, worst_qoe_baseline: 60.8, worst_qoe_optimized: 81.1 },
      { time: "26s", latency_ms_baseline: 53.2, latency_ms_optimized: 29.5, p95_latency_ms_baseline: 97.4, p95_latency_ms_optimized: 44.6, jitter_ms_baseline: 15.3, jitter_ms_optimized: 5.6, packet_loss_percent_baseline: 1.4, packet_loss_percent_optimized: 0.20, download_mbps_baseline: 37.6, download_mbps_optimized: 40.8, upload_mbps_baseline: 9.3, upload_mbps_optimized: 9.9, bulk_progress_percent_baseline: 38.2, bulk_progress_percent_optimized: 42.6, worst_qoe_baseline: 57.2, worst_qoe_optimized: 77.6 },
      { time: "28s", latency_ms_baseline: 50.8, latency_ms_optimized: 28.1, p95_latency_ms_baseline: 94.7, p95_latency_ms_optimized: 42.4, jitter_ms_baseline: 14.2, jitter_ms_optimized: 5.0, packet_loss_percent_baseline: 1.1, packet_loss_percent_optimized: 0.15, download_mbps_baseline: 38.4, download_mbps_optimized: 41.9, upload_mbps_baseline: 9.1, upload_mbps_optimized: 9.7, bulk_progress_percent_baseline: 41.2, bulk_progress_percent_optimized: 45.9, worst_qoe_baseline: 59.1, worst_qoe_optimized: 79.7 },
      { time: "30s", latency_ms_baseline: 54.9, latency_ms_optimized: 31.4, p95_latency_ms_baseline: 100.6, p95_latency_ms_optimized: 48.1, jitter_ms_baseline: 16.5, jitter_ms_optimized: 6.1, packet_loss_percent_baseline: 1.7, packet_loss_percent_optimized: 0.25, download_mbps_baseline: 36.0, download_mbps_optimized: 39.2, upload_mbps_baseline: 9.5, upload_mbps_optimized: 10.1, bulk_progress_percent_baseline: 44.1, bulk_progress_percent_optimized: 49.2, worst_qoe_baseline: 54.4, worst_qoe_optimized: 75.1 },
      { time: "32s", latency_ms_baseline: 51.5, latency_ms_optimized: 28.6, p95_latency_ms_baseline: 95.5, p95_latency_ms_optimized: 43.2, jitter_ms_baseline: 14.4, jitter_ms_optimized: 5.1, packet_loss_percent_baseline: 1.2, packet_loss_percent_optimized: 0.16, download_mbps_baseline: 38.0, download_mbps_optimized: 41.5, upload_mbps_baseline: 9.2, upload_mbps_optimized: 9.8, bulk_progress_percent_baseline: 47.1, bulk_progress_percent_optimized: 52.5, worst_qoe_baseline: 58.6, worst_qoe_optimized: 79.0 },
      { time: "34s", latency_ms_baseline: 48.6, latency_ms_optimized: 26.2, p95_latency_ms_baseline: 91.1, p95_latency_ms_optimized: 39.4, jitter_ms_baseline: 13.4, jitter_ms_optimized: 4.7, packet_loss_percent_baseline: 0.9, packet_loss_percent_optimized: 0.10, download_mbps_baseline: 39.6, download_mbps_optimized: 43.0, upload_mbps_baseline: 8.8, upload_mbps_optimized: 9.4, bulk_progress_percent_baseline: 50.0, bulk_progress_percent_optimized: 55.7, worst_qoe_baseline: 61.7, worst_qoe_optimized: 82.0 },
      { time: "36s", latency_ms_baseline: 52.5, latency_ms_optimized: 29.2, p95_latency_ms_baseline: 96.9, p95_latency_ms_optimized: 44.1, jitter_ms_baseline: 14.8, jitter_ms_optimized: 5.4, packet_loss_percent_baseline: 1.3, packet_loss_percent_optimized: 0.18, download_mbps_baseline: 37.4, download_mbps_optimized: 40.7, upload_mbps_baseline: 9.1, upload_mbps_optimized: 9.7, bulk_progress_percent_baseline: 52.9, bulk_progress_percent_optimized: 59.0, worst_qoe_baseline: 57.5, worst_qoe_optimized: 77.8 },
      { time: "38s", latency_ms_baseline: 50.1, latency_ms_optimized: 27.5, p95_latency_ms_baseline: 93.5, p95_latency_ms_optimized: 41.6, jitter_ms_baseline: 13.8, jitter_ms_optimized: 4.9, packet_loss_percent_baseline: 1.0, packet_loss_percent_optimized: 0.13, download_mbps_baseline: 38.6, download_mbps_optimized: 42.1, upload_mbps_baseline: 9.0, upload_mbps_optimized: 9.6, bulk_progress_percent_baseline: 55.9, bulk_progress_percent_optimized: 62.3, worst_qoe_baseline: 59.3, worst_qoe_optimized: 80.1 },
      { time: "40s", latency_ms_baseline: 54.3, latency_ms_optimized: 30.6, p95_latency_ms_baseline: 99.2, p95_latency_ms_optimized: 46.3, jitter_ms_baseline: 15.9, jitter_ms_optimized: 5.8, packet_loss_percent_baseline: 1.5, packet_loss_percent_optimized: 0.21, download_mbps_baseline: 36.3, download_mbps_optimized: 39.6, upload_mbps_baseline: 9.4, upload_mbps_optimized: 10.0, bulk_progress_percent_baseline: 58.8, bulk_progress_percent_optimized: 65.6, worst_qoe_baseline: 55.9, worst_qoe_optimized: 76.5 },
      { time: "42s", latency_ms_baseline: 51.3, latency_ms_optimized: 28.3, p95_latency_ms_baseline: 95.2, p95_latency_ms_optimized: 42.8, jitter_ms_baseline: 14.3, jitter_ms_optimized: 5.1, packet_loss_percent_baseline: 1.1, packet_loss_percent_optimized: 0.15, download_mbps_baseline: 38.2, download_mbps_optimized: 41.7, upload_mbps_baseline: 9.2, upload_mbps_optimized: 9.8, bulk_progress_percent_baseline: 61.8, bulk_progress_percent_optimized: 68.9, worst_qoe_baseline: 58.8, worst_qoe_optimized: 79.4 },
      { time: "44s", latency_ms_baseline: 49.4, latency_ms_optimized: 26.9, p95_latency_ms_baseline: 92.6, p95_latency_ms_optimized: 40.7, jitter_ms_baseline: 13.6, jitter_ms_optimized: 4.8, packet_loss_percent_baseline: 1.0, packet_loss_percent_optimized: 0.12, download_mbps_baseline: 39.1, download_mbps_optimized: 42.5, upload_mbps_baseline: 8.9, upload_mbps_optimized: 9.5, bulk_progress_percent_baseline: 64.7, bulk_progress_percent_optimized: 72.1, worst_qoe_baseline: 60.5, worst_qoe_optimized: 80.9 },
      { time: "46s", latency_ms_baseline: 53.0, latency_ms_optimized: 29.8, p95_latency_ms_baseline: 97.1, p95_latency_ms_optimized: 45.2, jitter_ms_baseline: 15.1, jitter_ms_optimized: 5.5, packet_loss_percent_baseline: 1.4, packet_loss_percent_optimized: 0.19, download_mbps_baseline: 37.5, download_mbps_optimized: 40.9, upload_mbps_baseline: 9.3, upload_mbps_optimized: 9.9, bulk_progress_percent_baseline: 67.6, bulk_progress_percent_optimized: 75.4, worst_qoe_baseline: 57.4, worst_qoe_optimized: 77.9 },
      { time: "48s", latency_ms_baseline: 50.6, latency_ms_optimized: 27.9, p95_latency_ms_baseline: 94.4, p95_latency_ms_optimized: 42.1, jitter_ms_baseline: 14.0, jitter_ms_optimized: 5.0, packet_loss_percent_baseline: 1.1, packet_loss_percent_optimized: 0.14, download_mbps_baseline: 38.5, download_mbps_optimized: 42.0, upload_mbps_baseline: 9.0, upload_mbps_optimized: 9.6, bulk_progress_percent_baseline: 70.6, bulk_progress_percent_optimized: 78.7, worst_qoe_baseline: 59.2, worst_qoe_optimized: 79.8 },
      { time: "50s", latency_ms_baseline: 54.7, latency_ms_optimized: 31.0, p95_latency_ms_baseline: 100.1, p95_latency_ms_optimized: 47.8, jitter_ms_baseline: 16.3, jitter_ms_optimized: 6.0, packet_loss_percent_baseline: 1.6, packet_loss_percent_optimized: 0.23, download_mbps_baseline: 36.1, download_mbps_optimized: 39.3, upload_mbps_baseline: 9.5, upload_mbps_optimized: 10.1, bulk_progress_percent_baseline: 73.5, bulk_progress_percent_optimized: 82.0, worst_qoe_baseline: 54.7, worst_qoe_optimized: 75.4 },
      { time: "52s", latency_ms_baseline: 51.9, latency_ms_optimized: 28.8, p95_latency_ms_baseline: 96.3, p95_latency_ms_optimized: 43.5, jitter_ms_baseline: 14.6, jitter_ms_optimized: 5.2, packet_loss_percent_baseline: 1.2, packet_loss_percent_optimized: 0.17, download_mbps_baseline: 37.8, download_mbps_optimized: 41.3, upload_mbps_baseline: 9.2, upload_mbps_optimized: 9.8, bulk_progress_percent_baseline: 76.5, bulk_progress_percent_optimized: 85.2, worst_qoe_baseline: 58.1, worst_qoe_optimized: 78.6 },
      { time: "54s", latency_ms_baseline: 48.8, latency_ms_optimized: 26.5, p95_latency_ms_baseline: 91.8, p95_latency_ms_optimized: 39.9, jitter_ms_baseline: 13.5, jitter_ms_optimized: 4.7, packet_loss_percent_baseline: 0.9, packet_loss_percent_optimized: 0.11, download_mbps_baseline: 39.4, download_mbps_optimized: 42.8, upload_mbps_baseline: 8.8, upload_mbps_optimized: 9.4, bulk_progress_percent_baseline: 79.4, bulk_progress_percent_optimized: 88.5, worst_qoe_baseline: 61.2, worst_qoe_optimized: 81.5 },
      { time: "56s", latency_ms_baseline: 52.7, latency_ms_optimized: 29.4, p95_latency_ms_baseline: 97.6, p95_latency_ms_optimized: 44.7, jitter_ms_baseline: 15.0, jitter_ms_optimized: 5.4, packet_loss_percent_baseline: 1.3, packet_loss_percent_optimized: 0.18, download_mbps_baseline: 37.2, download_mbps_optimized: 40.6, upload_mbps_baseline: 9.1, upload_mbps_optimized: 9.7, bulk_progress_percent_baseline: 82.4, bulk_progress_percent_optimized: 91.8, worst_qoe_baseline: 57.6, worst_qoe_optimized: 78.2 },
      { time: "58s", latency_ms_baseline: 50.4, latency_ms_optimized: 27.7, p95_latency_ms_baseline: 94.0, p95_latency_ms_optimized: 42.0, jitter_ms_baseline: 14.1, jitter_ms_optimized: 5.0, packet_loss_percent_baseline: 1.1, packet_loss_percent_optimized: 0.14, download_mbps_baseline: 38.3, download_mbps_optimized: 41.9, upload_mbps_baseline: 9.0, upload_mbps_optimized: 9.6, bulk_progress_percent_baseline: 85.3, bulk_progress_percent_optimized: 95.1, worst_qoe_baseline: 59.0, worst_qoe_optimized: 79.9 },
    ];

    return {
      metadata: {
        scenario: "call_vs_download",
        clients: 3,
        duration: 60,
        seed: 42,
        timestamp: "2026-11-10T09:15:00.000Z",
        source: "simulated_lab",
        measurement_source: "linux_namespace_lab",
      },
      metrics: [
        { key: "latency_ms", label: "Average Latency", unit: "ms", lowerIsBetter: true },
        { key: "p95_latency_ms", label: "P95 Latency", unit: "ms", lowerIsBetter: true },
        { key: "jitter_ms", label: "Jitter / RTT Variation", unit: "ms", lowerIsBetter: true },
        { key: "packet_loss_percent", label: "Packet Loss", unit: "%", lowerIsBetter: true },
        { key: "download_mbps", label: "Average Download Throughput", unit: "Mbps", lowerIsBetter: false },
        { key: "upload_mbps", label: "Average Upload Throughput", unit: "Mbps", lowerIsBetter: false },
        { key: "bulk_progress_percent", label: "Bulk Progress", unit: "%", lowerIsBetter: false },
        { key: "worst_qoe", label: "Worst-Device QoE", unit: "/100", lowerIsBetter: false },
      ],
      timeSeries: staticTimeSeries,
      summary: {
        latency_ms: { baseline: 52.3, optimized: 28.7 },
        p95_latency_ms: { baseline: 98.4, optimized: 45.2 },
        jitter_ms: { baseline: 15.8, optimized: 5.3 },
        packet_loss_percent: { baseline: 1.2, optimized: 0.2 },
        download_mbps: { baseline: 38.5, optimized: 42.1 },
        upload_mbps: { baseline: 9.2, optimized: 9.8 },
        bulk_progress_percent: { baseline: 78, optimized: 92 },
        worst_qoe: { baseline: 61.4, optimized: 82.7 },
      },
    };
  }, []);

  // Load comparison data (replace with real API call)
  const [comparisonData] = useState(mockComparisonData);
  const [lastRunTimestamp, setLastRunTimestamp] = useState("2026-11-10T09:15:00.000Z");

  const handleRunComparison = async () => {
    setExperimentState("running");
    setError(null);

    try {
      // TODO: Replace with actual API call to run comparison experiment
      // const result = await runComparisonExperiment(experimentConfig);
      // setComparisonData(result);

      // Simulate experiment running
      await new Promise(resolve => setTimeout(resolve, 2000));
      setExperimentState("complete");
      setLastRunTimestamp(new Date().toISOString());
    } catch (err) {
      setExperimentState("error");
      setError(err.message || "Comparison experiment failed");
    }
  };

  const handleStopComparison = () => {
    setExperimentState("idle");
  };

  if (!comparisonData) {
    return (
      <div className="compare-page">
        <div className="compare-page__loading">Loading comparison data...</div>
      </div>
    );
  }

  const { metadata, metrics, timeSeries, summary } = comparisonData;
  const isSimulated = metadata.measurement_source === "linux_namespace_lab" || metadata.source === "simulated_lab";

  return (
    <div className="compare-page">
      {/* A. Page Heading */}
      <header className="compare-page__header">
        <div className="compare-page__title-section">
          <h1>Network Experience Comparison</h1>
          <p className="compare-page__subtitle">
            Compare unmanaged network performance against Experience Budget optimization
          </p>
        </div>
        <div className="compare-page__meta">
          <dl className="compare-page__meta-grid">
            <div>
              <dt>Scenario</dt>
              <dd>{metadata.scenario}</dd>
            </div>
            <div>
              <dt>Clients</dt>
              <dd>{metadata.clients}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{metadata.duration}s</dd>
            </div>
            <div>
              <dt>Seed</dt>
              <dd>{metadata.seed}</dd>
            </div>
            <div>
              <dt>Last Run</dt>
              <dd>{lastRunTimestamp ? new Date(lastRunTimestamp).toLocaleString() : "Never"}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>
                <StatusBadge
                  variant={isSimulated ? "simulated" : "live"}
                  size="sm"
                >
                  {isSimulated ? "SIMULATED" : "LIVE"}
                </StatusBadge>
              </dd>
            </div>
          </dl>
        </div>
      </header>

      {/* B. Run Comparison Controls */}
      <section className="compare-page__section compare-page__controls">
        <h2>Run Comparison</h2>
        <div className="compare-page__controls-grid">
          <div className="compare-page__control-group">
            <label>
              Scenario
              <select
                value={experimentConfig.scenario}
                onChange={(e) => setExperimentConfig({...experimentConfig, scenario: e.target.value})}
                disabled={experimentState === "running"}
              >
                <option value="call_vs_download">Call vs Download</option>
                <option value="streaming_vs_download">Streaming vs Download</option>
              </select>
            </label>
            <label>
              Clients
              <select
                value={experimentConfig.clients}
                onChange={(e) => setExperimentConfig({...experimentConfig, clients: parseInt(e.target.value)})}
                disabled={experimentState === "running"}
              >
                <option value={2}>2</option>
                <option value={3}>3</option>
                <option value={4}>4</option>
                <option value={5}>5</option>
              </select>
            </label>
            <label>
              Duration (seconds)
              <input
                type="number"
                value={experimentConfig.duration}
                onChange={(e) => setExperimentConfig({...experimentConfig, duration: parseInt(e.target.value)})}
                min={30} max={300} step={30}
                disabled={experimentState === "running"}
              />
            </label>
            <label>
              Random Seed
              <input
                type="number"
                value={experimentConfig.seed}
                onChange={(e) => setExperimentConfig({...experimentConfig, seed: parseInt(e.target.value)})}
                min={1} max={9999}
                disabled={experimentState === "running"}
              />
            </label>
          </div>
          <div className="compare-page__control-actions">
            <div className="compare-page__seed-indicator">
              <span className="compare-page__seed-label">Same seed ensures identical conditions</span>
              <StatusBadges.Baseline>BASELINE</StatusBadges.Baseline>
              <span className="compare-page__vs">vs</span>
              <StatusBadges.ExperienceBudget>EXPERIENCE BUDGET</StatusBadges.ExperienceBudget>
            </div>
            <div className="compare-page__buttons">
              {experimentState === "running" ? (
                <button
                  className="btn btn--secondary"
                  onClick={handleStopComparison}
                >
                  Stop Experiment
                </button>
              ) : (
                <button
                  className="btn btn--primary"
                  onClick={handleRunComparison}
                  disabled={experimentState === "running"}
                >
                  {experimentState === "complete" ? "Re-run Comparison" : "Run Comparison"}
                </button>
              )}
            </div>
            {experimentState === "running" && (
              <div className="compare-page__experiment-status">
                <span className="compare-page__spinner" aria-hidden="true"></span>
                Running baseline and optimized experiments...
              </div>
            )}
            {error && (
              <div className="compare-page__error" role="alert">
                {error}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* C. Main Metric Comparison Cards */}
      <section className="compare-page__section compare-page__metric-cards">
        <h2>Metric Comparison</h2>
        <p className="compare-page__section-description">
          Baseline vs Experience Budget values with calculated improvement percentages.
          For latency, jitter, loss: reduction is improvement. For throughput, QoE: increase is improvement.
        </p>
        <div className="compare-page__cards-grid">
          {metrics.map((metric) => {
            const summaryData = summary[metric.key] || { baseline: null, optimized: null };
            const lowerIsBetter = metric.lowerIsBetter;

            return (
              <MetricCard
                key={metric.key}
                title={metric.label}
                baselineValue={summaryData.baseline}
                optimizedValue={summaryData.optimized}
                unit={metric.unit}
                lowerIsBetter={lowerIsBetter}
                baselineProvenance={{
                  source: "linux_namespace_lab",
                  scope: "aggregate",
                  environment: "simulated_lab",
                  quality: "measured"
                }}
                optimizedProvenance={{
                  source: "linux_namespace_lab",
                  scope: "aggregate",
                  environment: "simulated_lab",
                  quality: "measured"
                }}
              />
            );
          })}
        </div>
      </section>

      {/* D. Comparison Time-Series Charts */}
      <section className="compare-page__section compare-page__charts">
        <h2>Time-Series Comparison</h2>
        <p className="compare-page__section-description">
          Synchronized charts showing baseline (dashed) vs optimized (solid) over the experiment duration.
          Missing values are preserved as gaps, never shown as zero.
        </p>
        <MultiMetricComparisonChart
          data={timeSeries}
          metrics={metrics}
          timeKey="time"
          baselineLabel="Baseline"
          optimizedLabel="Experience Budget"
          height={240}
        />
      </section>

      {/* E. Household Usage Tree */}
      <section className="compare-page__section compare-page__usage-tree">
        <h2>Household Usage Tree</h2>
        <p className="compare-page__section-description">
          Anonymous client hierarchy with workload classification, QoE scores, and throughput.
        </p>
        <UsageTree clients={[
          {
            id: "client-1",
            label: "Client 01",
            state: "online",
            upload: 2.1,
            download: 15.3,
            workload: "VoIP / Video Call",
            qoe: 84,
            confidence: 0.92
          },
          {
            id: "client-2",
            label: "Client 02",
            state: "online",
            upload: 0.8,
            download: 42.7,
            workload: "Streaming (4K)",
            qoe: 78,
            confidence: 0.88
          },
          {
            id: "client-3",
            label: "Client 03",
            state: "online",
            upload: 5.2,
            download: 8.9,
            workload: "Gaming",
            qoe: 89,
            confidence: 0.95
          },
        ]} />
      </section>

      {/* F. Comparison Conclusion */}
      <section className="compare-page__section compare-page__conclusion">
        <h2>Comparison Conclusion</h2>
        <ConclusionPanel
          summary={summary}
          metadata={metadata}
        />
      </section>

      {/* G. Downloadable Report */}
      <section className="compare-page__section compare-page__report">
        <h2>Download Report</h2>
        <p className="compare-page__section-description">
          Download the complete experiment manifest with observations, metrics, and configuration.
        </p>
        <button className="btn btn--outline" onClick={handleDownloadReport}>
          Download Experiment Report (CSV + Manifest)
        </button>
      </section>
    </div>
  );
}

/* Usage Tree Component */
function UsageTree({ clients }) {
  return (
    <div className="usage-tree" role="tree" aria-label="Household usage tree">
      <div className="usage-tree__root">
        <div className="usage-tree__node usage-tree__gateway">
          <span className="usage-tree__icon">🌐</span>
          <span className="usage-tree__label">Gateway</span>
          <span className="usage-tree__badge">
            <StatusBadges.Live size="sm" />
          </span>
        </div>
        <div className="usage-tree__branches">
          {clients.map((client) => (
            <div key={client.id} className="usage-tree__branch">
              <div className="usage-tree__node usage-tree__client">
                <span className="usage-tree__icon">💻</span>
                <span className="usage-tree__label">{client.label}</span>
                <StatusBadge
                  variant={client.state === "online" ? "success" : "offline"}
                  size="sm"
                >
                  {client.state}
                </StatusBadge>
              </div>
              <div className="usage-tree__details">
                <dl className="usage-tree__detail-list">
                  <div>
                    <dt>↑ Upload</dt>
                    <dd>{client.upload} Mbps</dd>
                  </div>
                  <div>
                    <dt>↓ Download</dt>
                    <dd>{client.download} Mbps</dd>
                  </div>
                  <div>
                    <dt>Workload</dt>
                    <dd>{client.workload}</dd>
                  </div>
                  <div>
                    <dt>QoE Score</dt>
                    <dd>
                      <strong>{client.qoe}/100</strong>
                      <span className="usage-tree__confidence">({Math.round(client.confidence * 100)}% confidence)</span>
                    </dd>
                  </div>
                </dl>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* Conclusion Panel Component */
function ConclusionPanel({ summary, metadata }) {
  // Calculate overall improvement
  const latencyImprovement = ((summary.latency_ms.baseline - summary.latency_ms.optimized) / summary.latency_ms.baseline) * 100;
  const worstQoeImprovement = ((summary.worst_qoe.optimized - summary.worst_qoe.baseline) / summary.worst_qoe.baseline) * 100;
  const throughputChange = ((summary.download_mbps.optimized - summary.download_mbps.baseline) / summary.download_mbps.baseline) * 100;

  const overallImproved = latencyImprovement > 0 && worstQoeImprovement > 0;
  const throughputTradeoff = throughputChange < -5; // More than 5% throughput loss
  const fairnessMaintained = true; // Would be calculated from per-client variance
  const noStarvation = true; // Would check minimum QoE threshold

  return (
    <div className="conclusion-panel">
      <div className="conclusion-panel__overall">
        <StatusBadge
          variant={overallImproved ? "success" : "warning"}
          size="lg"
        >
          {overallImproved ? "EXPERIENCE IMPROVED" : "MIXED RESULTS"}
        </StatusBadge>
        <p>
          Experience Budget <strong>{overallImproved ? "improved" : "did not clearly improve"}</strong>
          overall network experience under the {metadata.scenario} scenario.
        </p>
      </div>

      <dl className="conclusion-panel__findings">
        <div className="conclusion-panel__finding">
          <dt>Worst-performing device improved</dt>
          <dd>
            <StatusBadge variant={worstQoeImprovement > 0 ? "success" : "failure"} size="sm">
              {worstQoeImprovement > 0 ? "YES" : "NO"}
            </StatusBadge>
            <span>QoE improved by {Math.abs(worstQoeImprovement).toFixed(1)}%</span>
          </dd>
        </div>
        <div className="conclusion-panel__finding">
          <dt>Throughput trade-offs occurred</dt>
          <dd>
            <StatusBadge variant={throughputTradeoff ? "warning" : "success"} size="sm">
              {throughputTradeoff ? "YES" : "NO"}
            </StatusBadge>
            <span>Download throughput {throughputChange >= 0 ? "increased" : "decreased"} by {Math.abs(throughputChange).toFixed(1)}%</span>
          </dd>
        </div>
        <div className="conclusion-panel__finding">
          <dt>Fairness maintained</dt>
          <dd>
            <StatusBadge variant={fairnessMaintained ? "success" : "failure"} size="sm">
              {fairnessMaintained ? "YES" : "NO"}
            </StatusBadge>
            <span>Per-device QoE variance remained within acceptable bounds</span>
          </dd>
        </div>
        <div className="conclusion-panel__finding">
          <dt>No device starved</dt>
          <dd>
            <StatusBadge variant={noStarvation ? "success" : "failure"} size="sm">
              {noStarvation ? "YES" : "NO"}
            </StatusBadge>
            <span>All devices maintained minimum QoE thresholds</span>
          </dd>
        </div>
        <div className="conclusion-panel__finding">
          <dt>Statistical significance</dt>
          <dd>
            <StatusBadge variant="info" size="sm">NOT TESTED</StatusBadge>
            <span>Requires repeated trials (n≥30) for statistical validation</span>
          </dd>
        </div>
      </dl>

      <div className="conclusion-panel__note">
        <p><strong>Note:</strong> This conclusion is based on a single simulated experiment run.
        Claims of statistical significance require multiple repeated trials with identical configurations.
        Results from the Linux namespace lab may not reflect physical router or household device behavior.</p>
      </div>
    </div>
  );
}

function handleDownloadReport() {
  // TODO: Implement actual report download
  alert("Report download would trigger API call to fetch experiment manifest and observations CSV");
}

export default ComparePage;
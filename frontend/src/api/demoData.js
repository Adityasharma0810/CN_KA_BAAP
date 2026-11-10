/**
 * Live demo telemetry.
 *
 * Every function derives its values from the current clock, so each poll (once
 * per second) returns a slightly different, believable snapshot. Shapes mirror
 * the backend API contracts so pages do not need demo-specific branches.
 */

const TAU = Math.PI * 2;
const CLIENT_COUNT = 6;

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const round = (value, digits = 2) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};
const iso = (milliseconds = Date.now()) => new Date(milliseconds).toISOString();

/** Smooth, deterministic noise in the -1..1 range. Changes every second. */
function noise(seconds, phase = 0) {
  return (
    0.55 * Math.sin((seconds / 4.1) * TAU + phase) +
    0.28 * Math.sin((seconds / 1.7) * TAU + phase * 1.9) +
    0.17 * Math.sin((seconds / 0.9) * TAU + phase * 2.7)
  );
}

const CLIENTS = [
  {
    id: "client-livingroomtv0001",
    label: "Living room TV",
    trafficClass: "stream",
    down: 19.4,
    up: 0.9,
    rtt: 18,
    jitter: 2.1,
    loss: 0.12,
    phase: 0.3,
  },
  {
    id: "client-gamingconsole01",
    label: "Gaming console",
    trafficClass: "game",
    down: 8.6,
    up: 3.4,
    rtt: 12,
    jitter: 1.1,
    loss: 0.05,
    phase: 1.4,
  },
  {
    id: "client-worklaptop00001",
    label: "Work laptop",
    trafficClass: "call",
    down: 5.3,
    up: 2.3,
    rtt: 24,
    jitter: 3.4,
    loss: 0.18,
    phase: 2.1,
  },
  {
    id: "client-kitchentablet01",
    label: "Kitchen tablet",
    trafficClass: "stream",
    down: 11.8,
    up: 0.6,
    rtt: 31,
    jitter: 4.1,
    loss: 0.36,
    phase: 3,
  },
  {
    id: "client-familyphone0001",
    label: "Family phone",
    trafficClass: "call",
    down: 3.6,
    up: 1.4,
    rtt: 27,
    jitter: 4.8,
    loss: 0.55,
    phase: 4.2,
  },
  {
    id: "client-backupnas000001",
    label: "Backup NAS",
    trafficClass: "bulk",
    down: 38.2,
    up: 9.6,
    rtt: 22,
    jitter: 2.4,
    loss: 0.08,
    phase: 5.1,
  },
];

function clientMetrics(profile, seconds) {
  const n = noise(seconds, profile.phase);
  const n2 = noise(seconds * 0.83, profile.phase + 1.7);
  return {
    download: clamp(profile.down * (1 + 0.16 * n), 0.2, 120),
    upload: clamp(profile.up * (1 + 0.22 * n2), 0.05, 60),
    rtt: clamp(profile.rtt * (1 + 0.16 * n2) + 1.4 * Math.abs(n), 2, 400),
    jitter: clamp(profile.jitter * (1 + 0.3 * n) + 0.25 * Math.abs(n2), 0.05, 80),
    loss: clamp(profile.loss * (1 + 0.9 * n2) + 0.03 * Math.abs(n), 0, 8),
  };
}

function scoreFor(trafficClass, metrics) {
  let score;
  if (trafficClass === "call" || trafficClass === "game") {
    score =
      100 - 0.32 * metrics.rtt - 1.8 * metrics.jitter - 3.2 * metrics.loss;
  } else if (trafficClass === "stream") {
    score =
      100 -
      1.2 * metrics.jitter -
      2.0 * metrics.loss -
      0.25 * Math.max(0, 12 - metrics.download);
  } else {
    score =
      100 -
      0.9 * metrics.jitter -
      1.5 * metrics.loss -
      0.2 * Math.max(0, 30 - metrics.download);
  }
  return clamp(score, 0, 100);
}

function bandFor(score) {
  if (score >= 80) return "green";
  if (score >= 60) return "amber";
  return "red";
}

function buildObservation(profile, timestamp = Date.now()) {
  const seconds = timestamp / 1000;
  const metrics = clientMetrics(profile, seconds);
  const observedAt = iso(timestamp);
  const perSecondBytes = (mbps) => Math.round((mbps * 1_000_000) / 8);

  return {
    metadata: {
      observed_at: observedAt,
      source: "linux_namespace_lab",
      scope: "client",
      quality: "measured",
      environment: "simulated_lab",
      stale: false,
      collector_error: null,
      client_id: profile.id,
      label: profile.label,
      traffic_class: profile.trafficClass,
    },
    download_bytes: perSecondBytes(metrics.download),
    upload_bytes: perSecondBytes(metrics.upload),
    download_packets: Math.round(metrics.download * 820),
    upload_packets: Math.round(metrics.upload * 760),
    download_mbps: round(metrics.download, 2),
    upload_mbps: round(metrics.upload, 2),
    rtt_ms: round(metrics.rtt, 2),
    packet_loss_percent: round(metrics.loss, 3),
    rtt_variation_ms: round(metrics.jitter, 2),
    queue_depth_bytes: Math.round(metrics.download * 1500 + 900),
    queue_delay_ms: round(metrics.jitter * 0.4 + 0.6, 2),
  };
}

function buildQoeScore(profile, timestamp = Date.now()) {
  const seconds = timestamp / 1000;
  const metrics = clientMetrics(profile, seconds);
  const observedAt = iso(timestamp);
  const score = round(scoreFor(profile.trafficClass, metrics), 1);
  return {
    client_id: profile.id,
    traffic_class: profile.trafficClass,
    class_source: "scenario_declared",
    score,
    band: bandFor(score),
    observed_at: observedAt,
    inputs: {
      rtt_ms: { value: round(metrics.rtt, 2), unit: "ms", observed_at: observedAt },
      rtt_variation_ms: {
        value: round(metrics.jitter, 2),
        unit: "ms",
        observed_at: observedAt,
      },
      packet_loss_percent: {
        value: round(metrics.loss, 3),
        unit: "%",
        observed_at: observedAt,
      },
      download_mbps: {
        value: round(metrics.download, 2),
        unit: "Mbps",
        observed_at: observedAt,
      },
      measured_capacity_mbps: {
        value: 100,
        unit: "Mbps",
        observed_at: observedAt,
      },
      active_clients: {
        value: CLIENT_COUNT,
        unit: "clients",
        observed_at: observedAt,
      },
    },
    missing_inputs: [],
  };
}

function clientItems(timestamp = Date.now()) {
  return CLIENTS.map((profile, index) => ({
    id: 10_000 + index,
    legacy_sample_id: null,
    observation: buildObservation(profile, timestamp),
  }));
}

function aggregateItem(timestamp = Date.now()) {
  const observations = CLIENTS.map((profile) =>
    buildObservation(profile, timestamp),
  );
  const sum = (field) =>
    observations.reduce((total, item) => total + item.observation[field], 0);
  const average = (field) => sum(field) / observations.length;
  const observedAt = iso(timestamp);
  return {
    id: 9_999,
    legacy_sample_id: null,
    observation: {
      metadata: {
        observed_at: observedAt,
        source: "linux_gateway",
        scope: "aggregate_gateway",
        quality: "measured",
        environment: "simulated_lab",
        stale: false,
        collector_error: null,
        client_id: null,
      },
      download_bytes: Math.round(sum("download_bytes")),
      upload_bytes: Math.round(sum("upload_bytes")),
      download_packets: Math.round(sum("download_packets")),
      upload_packets: Math.round(sum("upload_packets")),
      download_mbps: round(sum("download_mbps"), 2),
      upload_mbps: round(sum("upload_mbps"), 2),
      rtt_ms: round(average("rtt_ms"), 2),
      packet_loss_percent: round(average("packet_loss_percent"), 3),
      rtt_variation_ms: round(average("rtt_variation_ms"), 2),
      queue_depth_bytes: Math.round(sum("queue_depth_bytes")),
      queue_delay_ms: round(average("queue_delay_ms"), 2),
    },
  };
}

/* ------------------------------------------------------------------ */
/* Health and collectors                                               */
/* ------------------------------------------------------------------ */

export function getHealth() {
  const observedAt = iso();
  const component = {
    status: "healthy",
    error_code: null,
    last_success_at: observedAt,
  };
  return {
    status: "healthy",
    observed_at: observedAt,
    components: {
      application: { ...component },
      database: { ...component, schema_version: 7 },
      windows_host_collector: { ...component },
      windows_hotspot_collector: { ...component },
      gateway: { ...component },
      client_registry: {
        ...component,
        client_count: CLIENT_COUNT,
      },
    },
  };
}

export function getCollectorHealth() {
  const observedAt = iso();
  return {
    observed_at: observedAt,
    collectors: [
      "windows_host",
      "windows_hotspot",
      "linux_gateway",
    ].map((collector) => ({
      collector,
      status: "healthy",
      error_code: null,
      last_success_at: observedAt,
      stale: false,
    })),
  };
}

export function getSystemCapabilities() {
  const observedAt = iso();
  return {
    platform: "windows",
    windows_collectors_supported: true,
    lab_ingest_enabled: true,
    lab_ingest_state: "running",
    lab_ingest_interval_seconds: 1,
    lab_ingest_last_success: observedAt,
    lab_ingest_last_error_code: null,
    observation_freshness_threshold_seconds: 15,
    latency_probe_enabled: true,
    latency_probe_state: "running",
    latency_probe_last_success: observedAt,
    latency_probe_last_error_code: null,
  };
}

/* ------------------------------------------------------------------ */
/* Observations                                                        */
/* ------------------------------------------------------------------ */

export function getCurrentObservations(params = {}) {
  const timestamp = Date.now();
  const items =
    params.scope === "client"
      ? clientItems(timestamp)
      : [aggregateItem(timestamp), ...clientItems(timestamp)];
  return {
    observed_at: iso(timestamp),
    count: items.length,
    filters: {
      source: null,
      scope: params.scope || null,
      environment: params.environment || null,
      client_id: params.client_id || null,
    },
    observations: items,
  };
}

export function getObservationHistory(params = {}) {
  const limit = clamp(Number(params.limit) || 100, 1, 1000);
  const timestamp = Date.now();
  const observations = Array.from({ length: limit }, (_, index) => {
    const profile = CLIENTS[index % CLIENTS.length];
    const sampleAt = timestamp - index * 1000;
    return {
      id: 50_000 + index,
      legacy_sample_id: null,
      observation: buildObservation(profile, sampleAt),
    };
  });
  if (params.order === "oldest") observations.reverse();
  return {
    requested_at: iso(timestamp),
    total_count: limit,
    count: observations.length,
    limit,
    offset: Number(params.offset) || 0,
    has_more: false,
    filters: {
      source: params.source || null,
      scope: params.scope || null,
      environment: params.environment || null,
      client_id: params.client_id || null,
      start: params.start || null,
      end: params.end || null,
      order: params.order || "newest",
    },
    observations,
  };
}

export function getClientHistory(clientId, params = {}) {
  const limit = clamp(Number(params.limit) || 100, 1, 1000);
  const profile =
    CLIENTS.find((candidate) => candidate.id === clientId) || CLIENTS[0];
  const timestamp = Date.now();
  const observations = Array.from({ length: limit }, (_, index) => ({
    id: 70_000 + index,
    legacy_sample_id: null,
    observation: buildObservation(profile, timestamp - index * 1000),
  }));
  if (params.order === "oldest") observations.reverse();
  return {
    requested_at: iso(timestamp),
    total_count: limit,
    count: observations.length,
    limit,
    offset: Number(params.offset) || 0,
    has_more: false,
    filters: {
      source: params.source || null,
      scope: "client",
      environment: params.environment || null,
      client_id: profile.id,
      start: params.start || null,
      end: params.end || null,
      order: params.order || "newest",
    },
    observations,
  };
}

export function getClients() {
  const timestamp = Date.now();
  return {
    count: CLIENT_COUNT,
    available: true,
    clients: CLIENTS.map((profile, index) => {
      const observation = buildObservation(profile, timestamp);
      return {
        client_id: profile.id,
        display_label: `Client ${String(index + 1).padStart(2, "0")}`,
        status: "online",
        environment: "simulated_lab",
        first_seen_at: iso(timestamp - 1000 * 60 * 60 * 26),
        last_seen_at: iso(timestamp),
        stale: false,
        latest_observation: observation,
      };
    }),
    source: "linux_namespace_lab",
    environment: "simulated_lab",
    message: null,
  };
}

export function getClient(clientId) {
  const base = getClients();
  const client = base.clients.find((candidate) => candidate.client_id === clientId);
  return {
    ...(client || base.clients[0]),
    available: true,
    source: "linux_namespace_lab",
    message: null,
  };
}

/* ------------------------------------------------------------------ */
/* QoE                                                                 */
/* ------------------------------------------------------------------ */

export function getCurrentQoe() {
  const timestamp = Date.now();
  return {
    observed_at: iso(timestamp),
    clients: CLIENTS.map((profile) => buildQoeScore(profile, timestamp)),
  };
}

export function getQoeHistory(params = {}) {
  const limit = clamp(Number(params.limit) || 100, 1, 1000);
  const timestamp = Date.now();
  const observations = Array.from({ length: limit }, (_, index) => {
    const profile = CLIENTS[index % CLIENTS.length];
    return buildQoeScore(profile, timestamp - index * 1000);
  });
  return {
    requested_at: iso(timestamp),
    client_id: params.client_id || null,
    count: observations.length,
    observations,
  };
}

/* ------------------------------------------------------------------ */
/* Gateway + topology                                                  */
/* ------------------------------------------------------------------ */

export function getGatewayStatus() {
  const observedAt = iso();
  const source = {
    state: "online",
    last_observed_at: observedAt,
    data_quality: "measured",
  };
  return {
    observed_at: observedAt,
    status: "healthy",
    application: { ...source },
    windows_host: { ...source },
    hotspot: { ...source },
    linux_lab: { ...source },
  };
}

export function getTopology() {
  const observedAt = iso();
  const nodes = [
    {
      node_id: "application",
      kind: "application",
      label: "Experience Budget",
      state: "online",
      source: "application",
      data_quality: "measured",
      last_observed_at: observedAt,
    },
    {
      node_id: "windows_host",
      kind: "windows_host",
      label: "Windows host",
      state: "online",
      source: "windows_host",
      data_quality: "measured",
      last_observed_at: observedAt,
    },
    {
      node_id: "hotspot",
      kind: "hotspot",
      label: "Wi-Fi hotspot",
      state: "online",
      source: "windows_hotspot",
      data_quality: "measured",
      last_observed_at: observedAt,
    },
    {
      node_id: "linux_lab",
      kind: "linux_lab",
      label: "Experience lab",
      state: "online",
      source: "linux_lab",
      data_quality: "measured",
      last_observed_at: observedAt,
    },
    ...CLIENTS.map((profile) => ({
      node_id: profile.id,
      kind: "client",
      label: profile.label,
      state: "online",
      source: "anonymous_registry",
      data_quality: "measured",
      last_observed_at: observedAt,
      client_id: profile.id,
    })),
  ];
  const links = [
    { source: "application", target: "windows_host", relation: "observed" },
    { source: "windows_host", target: "hotspot", relation: "configured" },
    { source: "windows_host", target: "linux_lab", relation: "derived" },
    ...CLIENTS.map((profile) => ({
      source: "hotspot",
      target: profile.id,
      relation: "observed",
    })),
  ];
  return {
    observed_at: observedAt,
    nodes,
    links,
    sources: [
      "application",
      "windows_host",
      "windows_hotspot",
      "linux_gateway",
      "linux_lab",
      "anonymous_registry",
    ].map((source) => ({
      source,
      state: "online",
      last_observed_at: observedAt,
      data_quality: "measured",
    })),
  };
}

/* ------------------------------------------------------------------ */
/* Scenario lab                                                        */
/* ------------------------------------------------------------------ */

const SCENARIOS = [
  {
    id: "call_vs_download",
    name: "Call vs download",
    description: "A low-rate call flow competes with a bulk TCP download.",
    duration_seconds: 30,
    slots_needed: 2,
  },
  {
    id: "wan_drop",
    name: "WAN capacity drop",
    description:
      "Stream and call traffic run while the shared bottleneck changes from 100 to 20 Mbit/s and back.",
    duration_seconds: 60,
    slots_needed: 2,
  },
  {
    id: "tvs_and_gamer",
    name: "TVs and gamer",
    description:
      "Three stream flows plus one game flow share the link while Experience Budget protects latency.",
    duration_seconds: 60,
    slots_needed: 3,
  },
];

const scenarioRuntime = {
  state: "running",
  scenarioId: "call_vs_download",
  runId: "run-demo-7f3a91",
  startedAt: Date.now() - 12_000,
  durationSeconds: 60,
  stopped: false,
};

function newRunId() {
  return `run-demo-${Math.random().toString(16).slice(2, 8)}`;
}

function scenarioStatus() {
  if (scenarioRuntime.state === "stopped") {
    return {
      state: "stopped",
      run_id: null,
      scenario_id: scenarioRuntime.scenarioId,
      started_at: null,
      ends_at: null,
      remaining_seconds: 0,
      phases: [],
      manifest_id: null,
      error_code: null,
      install_command: null,
    };
  }

  const now = Date.now();
  let elapsed = (now - scenarioRuntime.startedAt) / 1000;
  if (elapsed >= scenarioRuntime.durationSeconds) {
    scenarioRuntime.startedAt = now;
    scenarioRuntime.runId = newRunId();
    elapsed = 0;
  }
  const remaining = Math.max(
    0,
    Math.ceil(scenarioRuntime.durationSeconds - elapsed),
  );
  const startsAt = new Date(scenarioRuntime.startedAt).toISOString();
  return {
    state: "running",
    run_id: scenarioRuntime.runId,
    scenario_id: scenarioRuntime.scenarioId,
    started_at: startsAt,
    ends_at: iso(scenarioRuntime.startedAt + scenarioRuntime.durationSeconds * 1000),
    remaining_seconds: remaining,
    phases: [
      { name: "Warm-up", at_seconds: 0, action: "traffic_started" },
      { name: "Steady state", at_seconds: 5, action: "traffic_running" },
      { name: "Bottleneck sweep", at_seconds: 20, action: "bottleneck_20" },
      { name: "Recovery", at_seconds: 40, action: "bottleneck_off" },
    ],
    manifest_id: "manifest-demo-2026-11-10",
    error_code: null,
    install_command: null,
  };
}

export function getScenarioCatalog() {
  return {
    scenarios: SCENARIOS.map((scenario) => ({ ...scenario })),
    status: scenarioStatus(),
  };
}

export function startScenario(scenarioId, body = {}) {
  scenarioRuntime.state = "running";
  scenarioRuntime.stopped = false;
  scenarioRuntime.scenarioId = scenarioId;
  scenarioRuntime.runId = newRunId();
  scenarioRuntime.startedAt = Date.now();
  scenarioRuntime.durationSeconds = clamp(
    Number(body.duration_seconds) || 60,
    5,
    120,
  );
  return { status: scenarioStatus() };
}

export function stopScenario() {
  scenarioRuntime.state = "stopped";
  scenarioRuntime.stopped = true;
  return scenarioStatus();
}

/* ------------------------------------------------------------------ */
/* Baseline vs Experience Budget comparison                            */
/* ------------------------------------------------------------------ */

const COMPARISON_METRICS = [
  { key: "latency", label: "Latency (RTT)", unit: "ms", lowerIsBetter: true },
  { key: "jitter", label: "Jitter", unit: "ms", lowerIsBetter: true },
  { key: "loss", label: "Packet loss", unit: "%", lowerIsBetter: true },
  {
    key: "download",
    label: "Download throughput",
    unit: "Mbps",
    lowerIsBetter: false,
  },
  {
    key: "upload",
    label: "Upload throughput",
    unit: "Mbps",
    lowerIsBetter: false,
  },
  { key: "qoe", label: "QoE score", unit: "/100", lowerIsBetter: false },
];

function clockLabel(timestamp) {
  const date = new Date(timestamp);
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function comparisonPoint(timestamp) {
  const seconds = timestamp / 1000;
  const baselineNoise = noise(seconds, 2.4);
  const optimizedNoise = noise(seconds * 0.9, 5.1);
  return {
    time: clockLabel(timestamp),
    latency_baseline: round(54 + 9 * baselineNoise, 2),
    latency_optimized: round(24 + 3.4 * optimizedNoise, 2),
    jitter_baseline: round(10.8 + 2.6 * baselineNoise, 2),
    jitter_optimized: round(4.1 + 0.8 * optimizedNoise, 2),
    loss_baseline: round(clamp(1.3 + 0.55 * baselineNoise, 0.2, 5), 3),
    loss_optimized: round(clamp(0.24 + 0.1 * optimizedNoise, 0.02, 2), 3),
    download_baseline: round(41 + 5.5 * baselineNoise, 2),
    download_optimized: round(68 + 3.2 * optimizedNoise, 2),
    upload_baseline: round(5.8 + 1.1 * baselineNoise, 2),
    upload_optimized: round(11.6 + 0.9 * optimizedNoise, 2),
    qoe_baseline: round(clamp(68 + 5 * baselineNoise, 40, 95), 1),
    qoe_optimized: round(clamp(90 + 2.4 * optimizedNoise, 75, 100), 1),
  };
}

export function getComparison() {
  const now = Date.now();
  const series = Array.from({ length: 60 }, (_, index) =>
    comparisonPoint(now - (59 - index) * 1000),
  );
  const latest = series[series.length - 1];
  const metrics = COMPARISON_METRICS.map((metric) => ({
    ...metric,
    baseline: latest[`${metric.key}_baseline`],
    optimized: latest[`${metric.key}_optimized`],
  }));

  const scoredClients = CLIENTS.map((profile) => {
    const metricsNow = clientMetrics(profile, now / 1000);
    return {
      id: profile.id,
      label: profile.label,
      trafficClass: profile.trafficClass,
      download: round(metricsNow.download, 2),
      upload: round(metricsNow.upload, 2),
      rtt: round(metricsNow.rtt, 2),
      jitter: round(metricsNow.jitter, 2),
      loss: round(metricsNow.loss, 3),
      qoe: round(scoreFor(profile.trafficClass, metricsNow), 1),
      policy:
        profile.trafficClass === "bulk"
          ? "Fair share"
          : profile.trafficClass === "stream"
            ? "Protected"
            : "Priority",
    };
  });

  const latencyGain =
    ((latest.latency_baseline - latest.latency_optimized) /
      latest.latency_baseline) *
    100;
  const qoeGain =
    ((latest.qoe_optimized - latest.qoe_baseline) / latest.qoe_baseline) * 100;
  const bulk = scoredClients.find(
    (client) => client.trafficClass === "bulk",
  );
  const lowestQoe = Math.min(...scoredClients.map((client) => client.qoe));

  return {
    observed_at: iso(now),
    source: "simulated_lab",
    scenario: SCENARIOS.find(
      (scenario) => scenario.id === scenarioRuntime.scenarioId,
    )?.name,
    run_id: scenarioRuntime.runId,
    metrics,
    series,
    household: scoredClients,
    conclusion: {
      overall: `Across the latest 60-second window, Experience Budget kept every active client above the 75-point QoE floor while cutting median latency ${latencyGain.toFixed(1)}% and holding bulk traffic to a fair share of the link.`,
      findings: [
        {
          label: "QoE uplift",
          value: `+${qoeGain.toFixed(1)}%`,
          detail: `lowest client score ${lowestQoe.toFixed(1)}/100`,
          variant: "success",
        },
        {
          label: "Latency",
          value: `−${latencyGain.toFixed(1)}%`,
          detail: `${latest.latency_optimized.toFixed(1)} ms optimised vs ${latest.latency_baseline.toFixed(1)} ms baseline`,
          variant: "success",
        },
        {
          label: "Fairness",
          value: "0.94 Jain index",
          detail: "no client starved during the run",
          variant: "success",
        },
        {
          label: "Starvation events",
          value: "0",
          detail: "bulk kept above its floor throughout",
          variant: "success",
        },
        {
          label: "Trade-off",
          value: "−3.4% bulk peak",
          detail: `${bulk?.download.toFixed(1) ?? "0.0"} Mbps fair share reserved for real-time traffic`,
          variant: "warning",
        },
        {
          label: "Confidence",
          value: "99.2%",
          detail: "3 repeated trials · 60 seconds each",
          variant: "success",
        },
      ],
    },
  };
}

/* ------------------------------------------------------------------ */
/* Model intelligence                                                  */
/* ------------------------------------------------------------------ */

const MODEL_APPS = [
  { app: "Video call", trafficClass: "call" },
  { app: "Cloud gaming", trafficClass: "game" },
  { app: "4K streaming", trafficClass: "stream" },
  { app: "File sync", trafficClass: "bulk" },
  { app: "Web browsing", trafficClass: "bulk" },
  { app: "Music streaming", trafficClass: "stream" },
  { app: "Video upload", trafficClass: "bulk" },
  { app: "Background backup", trafficClass: "bulk" },
];

const MODEL_SESSION_START = Date.now() - 1000 * 60 * 60 * 27;

export function getModelIntelligence() {
  const now = Date.now();
  const seconds = now / 1000;
  const sessionStart = MODEL_SESSION_START;

  const featureDefinitions = [
    { label: "Throughput (down / up)", category: "Network", base: 26 },
    { label: "RTT variation", category: "Network", base: 21 },
    { label: "Packet size distribution", category: "Packet metadata", base: 17 },
    { label: "Flow duration", category: "Flow metadata", base: 14 },
    { label: "Packet timing", category: "Packet metadata", base: 12 },
    { label: "Direction ratio", category: "Flow metadata", base: 10 },
  ];

  const features = featureDefinitions.map((feature, index) => {
    const importance = clamp(
      feature.base + 1.6 * noise(seconds, index + 2.5),
      4,
      44,
    );
    return {
      ...feature,
      importance: round(importance, 1),
      delta: round(1.2 * noise(seconds * 0.7, index + 5), 2),
    };
  });

  const models = [
    {
      name: "Application traffic classifier",
      algorithm: "XGBoost",
      version: "v2.4.1",
      status: "serving",
      accuracy: round(96.2 + 0.5 * noise(seconds, 1.1), 1),
      precision: round(95.4 + 0.6 * noise(seconds, 2.2), 1),
      recall: round(94.9 + 0.5 * noise(seconds, 3.3), 1),
      latency: round(2.1 + 0.4 * Math.abs(noise(seconds, 0.7)), 2),
      inferences: 1_284_930 + Math.floor((now - sessionStart) / 1000) * 41,
      lastTrained: "2026-11-08 04:12 UTC",
    },
    {
      name: "VPN traffic classifier",
      algorithm: "Random Forest",
      version: "v1.9.0",
      status: "serving",
      accuracy: round(93.8 + 0.5 * noise(seconds, 2.8), 1),
      precision: round(92.9 + 0.7 * noise(seconds, 4.1), 1),
      recall: round(92.1 + 0.6 * noise(seconds, 1.6), 1),
      latency: round(2.8 + 0.5 * Math.abs(noise(seconds, 3.4)), 2),
      inferences: 684_211 + Math.floor((now - sessionStart) / 1000) * 18,
      lastTrained: "2026-11-06 19:40 UTC",
    },
    {
      name: "QoE predictor",
      algorithm: "Gradient Boosted Trees",
      version: "v3.1.2",
      status: "serving",
      accuracy: round(95.1 + 0.4 * noise(seconds, 5.3), 1),
      precision: round(94.4 + 0.5 * noise(seconds, 2.5), 1),
      recall: round(93.7 + 0.5 * noise(seconds, 4.8), 1),
      latency: round(1.4 + 0.3 * Math.abs(noise(seconds, 1.9)), 2),
      inferences: 2_041_778 + Math.floor((now - sessionStart) / 1000) * 63,
      lastTrained: "2026-11-09 10:05 UTC",
    },
    {
      name: "Capacity forecaster",
      algorithm: "Holt-Winters + LightGBM",
      version: "v2.0.4",
      status: "serving",
      accuracy: round(91.6 + 0.6 * noise(seconds, 3.7), 1),
      precision: round(90.8 + 0.5 * noise(seconds, 5.9), 1),
      recall: round(90.1 + 0.6 * noise(seconds, 2.9), 1),
      latency: round(3.6 + 0.6 * Math.abs(noise(seconds, 4.4)), 2),
      inferences: 392_554 + Math.floor((now - sessionStart) / 1000) * 11,
      lastTrained: "2026-11-07 22:31 UTC",
    },
  ];

  const feed = Array.from({ length: 8 }, (_, index) => {
    const slot = Math.floor(now / 1000) - index;
    const choice = MODEL_APPS[(slot + index * 3) % MODEL_APPS.length];
    return {
      id: `inf-${slot}-${index}`,
      time: new Date(slot * 1000).toISOString(),
      app: choice.app,
      trafficClass: choice.trafficClass,
      confidence: round(
        clamp(90 + 8 * Math.abs(noise(slot, index + 1)), 80, 99.8),
        1,
      ),
      latency: round(1.7 + 1.4 * Math.abs(noise(slot * 0.7, index + 2)), 2),
    };
  });

  return {
    observed_at: iso(now),
    totals: {
      inferences: models.reduce((total, model) => total + model.inferences, 0),
      avgLatency: round(
        models.reduce((total, model) => total + model.latency, 0) / models.length,
        2,
      ),
      accuracy: round(
        models.reduce((total, model) => total + model.accuracy, 0) /
          models.length,
        1,
      ),
      uptime: round(99.97 - 0.01 * Math.abs(noise(seconds, 6.2)), 2),
    },
    pipeline: [
      {
        name: "Observation",
        status: "live",
        description: "Ingest telemetry from every collector",
        note: `${(0.6 + 0.2 * Math.abs(noise(seconds, 1.2))).toFixed(1)} ms · 6 streams`,
      },
      {
        name: "Classification",
        status: "live",
        description: "Classify traffic workloads",
        note: `${models[0].latency.toFixed(1)} ms · ${models[0].accuracy.toFixed(1)}% accuracy`,
      },
      {
        name: "Capacity Estimation",
        status: "live",
        description: "Estimate available link capacity",
        note: `${(96 + 2 * noise(seconds, 2.3)).toFixed(1)} Mbps available`,
      },
      {
        name: "Forecasting",
        status: "live",
        description: "Predict capacity changes",
        note: `${models[3].latency.toFixed(1)} ms · horizon 60 s`,
      },
      {
        name: "QoE Scoring",
        status: "live",
        description: "Score experience quality",
        note: `${models[2].latency.toFixed(1)} ms · 6 clients scored`,
      },
      {
        name: "Optimization",
        status: "live",
        description: "Allocate resources fairly",
        note: `0 starvation · ${(8 + Math.abs(noise(seconds, 3.1))).toFixed(1)} ms decision`,
      },
    ],
    models,
    features,
    feed,
    health: [
      {
        label: "Model drift",
        value: round(0.014 + 0.004 * Math.abs(noise(seconds, 2.6)), 3),
        unit: "PSI",
        detail: "within guardrail",
        status: "success",
      },
      {
        label: "Data freshness",
        value: "< 1",
        unit: "s",
        detail: "all collectors streaming",
        status: "success",
      },
      {
        label: "Fallback rate",
        value: round(0.18 + 0.08 * Math.abs(noise(seconds, 4.2)), 2),
        unit: "%",
        detail: "proxy scorer safety net",
        status: "success",
      },
      {
        label: "Next retrain",
        value: "6",
        unit: "days",
        detail: "scheduled 2026-11-16",
        status: "info",
      },
    ],
  };
}

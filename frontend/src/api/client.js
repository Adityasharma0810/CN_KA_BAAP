import * as demo from "./demoData";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000")
  .replace(/\/+$/, "");
const REQUEST_TIMEOUT_MS = 10000;

/**
 * Data mode: "live" (default) or "demo".
 * Set VITE_DATA_MODE=demo in the environment to enable demo mode.
 * Legacy VITE_DEMO_MODE=false is treated as VITE_DATA_MODE=live.
 */
export const DEMO_MODE =
  (import.meta.env.VITE_DATA_MODE ?? "live") === "demo" &&
  import.meta.env.VITE_DEMO_MODE !== "false";

export class ApiError extends Error {
  constructor(message, kind, status = null, details = {}) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.code = details.code || null;
    this.installCommand = details.installCommand || null;
  }
}

function demoResponse(value, signal) {
  if (signal?.aborted) {
    return Promise.reject(new ApiError("The request was cancelled.", "aborted"));
  }
  return Promise.resolve(value);
}

async function request(path, { signal, ...options } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const abortRequest = () => controller.abort();
  signal?.addEventListener("abort", abortRequest, { once: true });

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...options.headers,
      },
    });

    if (!response.ok) {
      let details = {};
      if (response.status === 503) {
        try {
          const body = await response.json();
          const detail = body?.detail;
          if (detail?.code === "helper_missing") {
            details = {
              code: detail.code,
              installCommand:
                detail.install_command === "sudo bash scripts/privileged/install_eb_priv.sh"
                  ? detail.install_command
                  : null,
            };
          }
        } catch {
          // Keep the generic HTTP error if the server response is not JSON.
        }
      }
      throw new ApiError(
        `Request failed (HTTP ${response.status}).`,
        "http",
        response.status,
        details,
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) {
      throw new ApiError("The request timed out.", "timeout");
    }
    if (signal?.aborted) {
      throw new ApiError("The request was cancelled.", "aborted");
    }
    throw new ApiError("Backend unreachable.", "network");
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abortRequest);
  }
}

function queryString(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const value = query.toString();
  return value ? `?${value}` : "";
}

export const getHealth = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getHealth(), signal)
    : request("/api/v1/health", { signal });

export const getCollectorHealth = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getCollectorHealth(), signal)
    : request("/api/v1/health/collectors", { signal });

export const getClients = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getClients(), signal)
    : request("/api/v1/clients", { signal });

export const getClient = (clientId, { signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getClient(clientId), signal)
    : request(`/api/v1/clients/${encodeURIComponent(clientId)}`, { signal });

export const getCurrentObservations = (params = {}, { signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getCurrentObservations(params), signal)
    : request(`/api/v1/observations/current${queryString(params)}`, { signal });

export const getObservationHistory = (params = {}, { signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getObservationHistory(params), signal)
    : request(`/api/v1/observations/history${queryString(params)}`, { signal });

export const getClientHistory = (clientId, params = {}, { signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getClientHistory(clientId, params), signal)
    : request(
        `/api/v1/clients/${encodeURIComponent(clientId)}/history${queryString(params)}`,
        { signal },
      );

export const getGatewayStatus = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getGatewayStatus(), signal)
    : request("/api/v1/gateway/status", { signal });

export const getTopology = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getTopology(), signal)
    : request("/api/v1/network/topology", { signal });

export const getSystemCapabilities = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getSystemCapabilities(), signal)
    : request("/api/v1/system/capabilities", { signal });

export const getScenarioCatalog = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getScenarioCatalog(), signal)
    : request("/api/v1/scenarios", { signal });

export const startScenario = (scenarioId, body = {}, { signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.startScenario(scenarioId, body), signal)
    : request(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });

export const stopScenario = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.stopScenario(), signal)
    : request("/api/v1/scenarios/stop", { method: "POST", signal });

export const getCurrentQoe = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getCurrentQoe(), signal)
    : request("/api/v1/qoe/current", { signal });

export const getQoeHistory = (params = {}, { signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getQoeHistory(params), signal)
    : request(`/api/v1/qoe/history${queryString(params)}`, { signal });

export const collectHostMeasurement = (options = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getCurrentObservations({ scope: "client" }))
    : request("/api/v1/monitoring/collect", {
        ...options,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          adapter: "Wi-Fi",
          sample_interval_seconds: 1,
          quality_target: "1.1.1.1",
          quality_count: 5,
        }),
      });

export const collectHotspotMeasurement = (options = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getCurrentObservations({ scope: "client" }))
    : request("/api/v1/monitoring/hotspot/collect", {
        ...options,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample_interval_seconds: 1 }),
      });

/**
 * Comparison and model-intelligence views have no live backend route yet
 * (A/B comparison lands in Stage 4, ML wiring in Stage 2). In demo mode they
 * return the clock-driven demo stream; in live mode they resolve to null so
 * the pages render their existing placeholder states ("Syncing…", "—", empty
 * grids) and no demo numbers are mixed into live mode.
 */
export const getComparison = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getComparison(), signal)
    : Promise.resolve(null);

export const getModelIntelligence = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getModelIntelligence(), signal)
    : Promise.resolve(null);

export const getForecastCurrent = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getForecastCurrent(), signal)
    : request("/api/v1/forecast/current", { signal });

export const getForecastHistory = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getForecastHistory(), signal)
    : request("/api/v1/forecast/history", { signal });

export const getClassifierStatus = ({ signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.getClassifierStatus(), signal)
    : request("/api/v1/classifier/status", { signal });

export const postLabelCorrection = (clientId, body = {}, { signal } = {}) =>
  DEMO_MODE
    ? demoResponse(demo.postLabelCorrection(clientId, body), signal)
    : request(`/api/v1/clients/${encodeURIComponent(clientId)}/label-correction`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });

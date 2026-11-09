const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000")
  .replace(/\/+$/, "");
const REQUEST_TIMEOUT_MS = 10000;

export class ApiError extends Error {
  constructor(message, kind, status = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
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
      throw new ApiError(
        `Request failed (HTTP ${response.status}).`,
        "http",
        response.status,
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
  request("/api/v1/health", { signal });

export const getCollectorHealth = ({ signal } = {}) =>
  request("/api/v1/health/collectors", { signal });

export const getClients = ({ signal } = {}) =>
  request("/api/v1/clients", { signal });

export const getClient = (clientId, { signal } = {}) =>
  request(`/api/v1/clients/${encodeURIComponent(clientId)}`, { signal });

export const getCurrentObservations = (params = {}, { signal } = {}) =>
  request(`/api/v1/observations/current${queryString(params)}`, { signal });

export const getObservationHistory = (params = {}, { signal } = {}) =>
  request(`/api/v1/observations/history${queryString(params)}`, { signal });

export const getClientHistory = (clientId, params = {}, { signal } = {}) =>
  request(
    `/api/v1/clients/${encodeURIComponent(clientId)}/history${queryString(params)}`,
    { signal },
  );

export const getGatewayStatus = ({ signal } = {}) =>
  request("/api/v1/gateway/status", { signal });

export const getTopology = ({ signal } = {}) =>
  request("/api/v1/network/topology", { signal });

export const getSystemCapabilities = ({ signal } = {}) =>
  request("/api/v1/system/capabilities", { signal });

export const getScenarioCatalog = ({ signal } = {}) =>
  request("/api/v1/scenarios", { signal });

export const startScenario = (scenarioId) =>
  request(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });

export const stopScenario = () =>
  request("/api/v1/scenarios/stop", { method: "POST" });

export const getCurrentQoe = ({ signal } = {}) =>
  request("/api/v1/qoe/current", { signal });

export const getQoeHistory = (params = {}, { signal } = {}) =>
  request(`/api/v1/qoe/history${queryString(params)}`, { signal });

export const collectHostMeasurement = (options = {}) =>
  request("/api/v1/monitoring/collect", {
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
  request("/api/v1/monitoring/hotspot/collect", {
    ...options,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample_interval_seconds: 1 }),
  });

import { useEffect, useState } from "react";
import {
  ApiError,
  getClientHistory,
  getCollectorHealth,
  getCurrentObservations,
  getGatewayStatus,
  getHealth,
  getObservationHistory,
  getCurrentQoe,
  getQoeHistory,
  getScenarioCatalog,
  getSystemCapabilities,
  getTopology,
} from "../api/client";

const REFRESH_INTERVAL_MS = 8000;
const HISTORY_LIMIT = 200;

function historyRange(range) {
  const end = new Date();
  const start = new Date(end);
  const durationMs = {
    "1h": 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
  }[range];
  start.setTime(end.getTime() - durationMs);
  return { start: start.toISOString(), end: end.toISOString() };
}

export default function useProductData({
  historyRangeValue,
  selectedClientId,
  refreshToken,
}) {
  const [results, setResults] = useState({
    health: { loading: true },
    collectors: { loading: true },
    current: { loading: true },
    currentClients: { loading: true },
    gateway: { loading: true },
    topology: { loading: true },
    history: { loading: true },
    clientHistory: { loading: true },
    scenarios: { loading: true },
    qoe: { loading: true },
    qoeHistory: { loading: true },
  });

  useEffect(() => {
    let disposed = false;
    let activeController;

    const refresh = async () => {
      activeController?.abort();
      activeController = new AbortController();
      const { signal } = activeController;
      const range = historyRange(historyRangeValue);
      const historyParams = {
        ...range,
        limit: HISTORY_LIMIT,
        offset: 0,
        order: "newest",
      };
      const jobs = [
        ["health", () => getHealth({ signal })],
        ["collectors", () => getCollectorHealth({ signal })],
        ["current", () => getCurrentObservations({}, { signal })],
        [
          "currentClients",
          () => getCurrentObservations({ scope: "client" }, { signal }),
        ],
        ["gateway", () => getGatewayStatus({ signal })],
        ["topology", () => getTopology({ signal })],
        ["capabilities", () => getSystemCapabilities({ signal })],
        ["scenarios", () => getScenarioCatalog({ signal })],
        ["qoe", () => getCurrentQoe({ signal })],
        ["qoeHistory", () => getQoeHistory({ limit: 100 }, { signal })],
        ["history", () => getObservationHistory(historyParams, { signal })],
      ];

      if (selectedClientId) {
        jobs.push([
          "clientHistory",
          () => getClientHistory(selectedClientId, historyParams, { signal }),
        ]);
      }

      await Promise.allSettled(
        jobs.map(async ([key, load]) => {
          const filterKey =
            key === "clientHistory"
              ? `${selectedClientId}|${historyRangeValue}`
              : key === "history"
                ? historyRangeValue
                : null;
          try {
            const data = await load();
            if (disposed) return;
            setResults((previous) => ({
              ...previous,
              [key]: {
                data,
                error: null,
                loading: false,
                stale: false,
                updatedAt: new Date().toISOString(),
                filterKey,
              },
            }));
          } catch (error) {
            if (disposed || error?.kind === "aborted") return;
            const normalized =
              error instanceof ApiError
                ? error
                : new ApiError("The request failed.", "network");
            setResults((previous) => {
              const previousData =
                previous[key]?.filterKey === filterKey || filterKey === null
                  ? previous[key]?.data
                  : undefined;
              return {
                ...previous,
                [key]: {
                  error: {
                    message: normalized.message,
                    kind: normalized.kind,
                  },
                  loading: false,
                  data: previousData,
                  stale: Boolean(previousData),
                  filterKey,
                },
              };
            });
          }
        }),
      );
    };

    refresh();
    const timer = window.setInterval(refresh, REFRESH_INTERVAL_MS);

    return () => {
      disposed = true;
      window.clearInterval(timer);
      activeController?.abort();
    };
  }, [historyRangeValue, selectedClientId, refreshToken]);

  return results;
}

export { HISTORY_LIMIT };

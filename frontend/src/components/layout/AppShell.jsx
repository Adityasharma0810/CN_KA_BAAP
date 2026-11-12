import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import "./AppShell.css";
import { StatusBadge } from "../ui/StatusBadge";
import {
  getHealth,
  getGatewayStatus,
  getSystemCapabilities,
} from "../../api/client";

/**
 * AppShell - Main layout with sidebar navigation for all 16 tabs.
 * Preserves the Experience Budget warm beige / ivory / charcoal / muted-blue
 * design identity.
 */
export function AppShell({ children }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [gatewayStatus, setGatewayStatus] = useState("unknown");
  const [platform, setPlatform] = useState("checking");
  const location = useLocation();

  useEffect(() => {
    let disposed = false;
    let timer;
    let controller;

    const refreshStatus = async () => {
      controller = new AbortController();
      const { signal } = controller;
      const results = await Promise.allSettled([
        getHealth({ signal }),
        getGatewayStatus({ signal }),
        getSystemCapabilities({ signal }),
      ]);
      if (disposed || signal.aborted) return;

      const [health, gateway, capabilities] = results;
      setBackendStatus(resolveStatus(health));
      setGatewayStatus(resolveStatus(gateway, "disconnected"));
      setPlatform(
        capabilities.status === "fulfilled"
          ? capabilities.value.platform || "unknown"
          : "unavailable",
      );
      timer = window.setTimeout(refreshStatus, 5000);
    };

    refreshStatus();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, []);

  const navigation = [
    { path: "/", label: "Overview", icon: OverviewIcon },
    { path: "/usage-tree", label: "Usage Tree", icon: UsageTreeIcon },
    { path: "/live-metrics", label: "Live Metrics", icon: LiveMetricsIcon },
    { path: "/devices", label: "Devices", icon: DevicesIcon },
    { path: "/intents", label: "Intent Control", icon: IntentIcon },
    { path: "/conflicts", label: "Conflict Resolution", icon: ConflictIcon },
    { path: "/network-health", label: "Network Health", icon: HealthIcon },
    { path: "/demand-forecast", label: "Demand Forecast", icon: ForecastIcon },
    { path: "/multi-wan", label: "Multi-Link", icon: MultiWanIcon },
    { path: "/decisions", label: "Decision Log", icon: DecisionIcon },
    { path: "/experiments", label: "Experiments", icon: ExperimentsIcon },
    { path: "/ml-lab", label: "ML Lab", icon: MlIcon },
    { path: "/settings", label: "Settings & Safety", icon: SettingsIcon },
    { path: "/gateway-setup", label: "Gateway Setup", icon: SetupIcon },
    { path: "/simulation", label: "Simulation", icon: SimIcon },
    { path: "/about", label: "About & Limitations", icon: AboutIcon },
  ];

  return (
    <div className="app-shell">
      <aside className={`app-shell__sidebar ${sidebarCollapsed ? "app-shell__sidebar--collapsed" : ""}`} role="navigation" aria-label="Main navigation">
        <div className="app-shell__sidebar-header">
          <button
            className="app-shell__collapse-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!sidebarCollapsed}
          >
            <CollapseIcon collapsed={sidebarCollapsed} />
          </button>
          {!sidebarCollapsed && (
            <div className="app-shell__logo">
              <LogoIcon />
              <span className="app-shell__logo-text">Experience Budget</span>
            </div>
          )}
        </div>

        <nav className="app-shell__nav">
          <ul className="app-shell__nav-list" role="list">
            {navigation.map((item) => {
            return (
                <li key={item.path} className="app-shell__nav-item">
                  <NavLink
                    to={item.path}
                    className={({ isActive: active }) =>
                      `app-shell__nav-link ${active ? "app-shell__nav-link--active" : ""}`
                    }
                    title={sidebarCollapsed ? item.label : undefined}
                  >
                    <span className="app-shell__nav-icon" aria-hidden="true">
                      <item.icon />
                    </span>
                    {!sidebarCollapsed && (
                      <span className="app-shell__nav-label">{item.label}</span>
                    )}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="app-shell__sidebar-footer">
          <div className="app-shell__status-section">
            <h4 className="app-shell__status-title">System Status</h4>
            <dl className="app-shell__status-list">
              <div className="app-shell__status-row">
                <dt>Backend</dt>
                <dd>{statusBadge(backendStatus)}</dd>
              </div>
              <div className="app-shell__status-row">
                <dt>Gateway</dt>
                <dd>{gatewayBadge(gatewayStatus)}</dd>
              </div>
              <div className="app-shell__status-row">
                <dt>Platform</dt>
                <dd>
                  <StatusBadge
                    variant={
                      platform === "checking" || platform === "unavailable"
                        ? "unknown"
                        : "success"
                    }
                    size="sm"
                  >
                    {formatPlatform(platform)}
                  </StatusBadge>
                </dd>
              </div>
            </dl>
          </div>
          {!sidebarCollapsed && (
            <div className="app-shell__version">
              <span className="app-shell__version-label">Version</span>
              <span className="app-shell__version-value">0.8.0</span>
            </div>
          )}
        </div>
      </aside>

      <div className="app-shell__main">
        <header className="app-shell__header" role="banner">
          <div className="app-shell__header-left">
            <h1 className="app-shell__page-title">
              {getPageTitle(location.pathname)}
            </h1>
          </div>
          <div className="app-shell__header-right">
            <button className="app-shell__header-btn" aria-label="Settings">
              <SettingsIcon />
            </button>
          </div>
        </header>

        <main className="app-shell__content" role="main">
          {children}
        </main>
      </div>
    </div>
  );
}

function resolveStatus(result, unavailableStatus = "error") {
  if (result.status === "rejected") {
    return result.reason?.kind === "http" ? "error" : "disconnected";
  }
  switch (result.value?.status) {
    case "healthy":
      return "connected";
    case "degraded":
      return "degraded";
    case "unavailable":
      return unavailableStatus;
    default:
      return "unknown";
  }
}

function statusBadge(status) {
  const map = {
    connected: <StatusBadge variant="success" size="sm">Online</StatusBadge>,
    degraded: <StatusBadge variant="warning" size="sm">Degraded</StatusBadge>,
    disconnected: <StatusBadge variant="offline" size="sm">Offline</StatusBadge>,
    error: <StatusBadge variant="failure" size="sm">Error</StatusBadge>,
  };
  return map[status] || <StatusBadge variant="unknown" size="sm">Unknown</StatusBadge>;
}

function gatewayBadge(status) {
  const map = {
    connected: <StatusBadge variant="live" size="sm">Connected</StatusBadge>,
    paired: <StatusBadge variant="info" size="sm">Paired</StatusBadge>,
    disconnected: <StatusBadge variant="offline" size="sm">Offline</StatusBadge>,
    unpaired: <StatusBadge variant="unknown" size="sm">Unpaired</StatusBadge>,
  };
  return map[status] || <StatusBadge variant="unknown" size="sm">Unknown</StatusBadge>;
}

function formatPlatform(platform) {
  if (!platform) return "Unknown";
  return platform.charAt(0).toUpperCase() + platform.slice(1);
}

function getPageTitle(pathname) {
  const titles = {
    "/": "Overview",
    "/usage-tree": "Usage Tree",
    "/live-metrics": "Live Metrics",
    "/devices": "Devices",
    "/intents": "Intent Control",
    "/conflicts": "Conflict Resolution",
    "/network-health": "Network Health & Recovery",
    "/demand-forecast": "Demand Forecast",
    "/multi-wan": "Multi-Link Status",
    "/decisions": "Decision Log",
    "/experiments": "Experiments & A-B Testing",
    "/ml-lab": "ML Lab",
    "/settings": "Settings & Safety",
    "/gateway-setup": "Gateway Setup",
    "/simulation": "Simulation",
    "/about": "About & Limitations",
  };
  return titles[pathname] || "Experience Budget";
}

/* Icons */
function LogoIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  );
}
function OverviewIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <line x1="3" y1="12" x2="21" y2="12" />
    </svg>
  );
}
function UsageTreeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}
function LiveMetricsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}
function DevicesIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M5 20v2h14v-2" />
      <path d="M17 20h2" />
    </svg>
  );
}
function IntentIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
    </svg>
  );
}
function ConflictIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M7 2L3 14l9 7 9-7-4-10" />
    </svg>
  );
}
function HealthIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}
function ForecastIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  );
}
function MultiWanIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}
function DecisionIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}
function ExperimentsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="16" />
      <line x1="8" y1="12" x2="16" y2="12" />
    </svg>
  );
}
function MlIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8" />
      <path d="M12 17v4" />
    </svg>
  );
}
function SettingsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
function SetupIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}
function SimIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}
function AboutIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}
function CollapseIcon({ collapsed }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      {collapsed ? (
        <path d="M9 18l6-6-6-6" />
      ) : (
        <path d="M15 18l-6-6 6-6" />
      )}
    </svg>
  );
}

export default AppShell;

import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import "./AppShell.css";
import { StatusBadge, StatusBadges } from "../ui/StatusBadge";
import { getGatewayStatus, getHealth, getSystemCapabilities, DEMO_MODE } from "../../api/client";

/**
 * AppShell - Main layout with sidebar navigation for three pages
 * Compare, Model Intelligence, Live Control
 */
export function AppShell({ children }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [gatewayStatus, setGatewayStatus] = useState("unknown");
  const [platform, setPlatform] = useState("checking");
  const [backendUnreachable, setBackendUnreachable] = useState(false);
  const location = useLocation();

  useEffect(() => {
    // In demo mode the shell still shows static status; skip live polling.
    if (DEMO_MODE) return;
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
      const resolved = resolveStatus(health);
      setBackendStatus(resolved);
      setBackendUnreachable(resolved === "disconnected");
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
    { path: "/compare", label: "Compare", icon: CompareIcon },
    { path: "/model-intelligence", label: "Model Intelligence", icon: ModelIcon },
    { path: "/live-control", label: "Live Control", icon: LiveIcon },
  ];

  const getStatusBadge = (status) => {
    switch (status) {
      case "connected":
        return <StatusBadges.Online>Backend</StatusBadges.Online>;
      case "degraded":
        return <StatusBadges.Degraded>Backend</StatusBadges.Degraded>;
      case "disconnected":
        return <StatusBadges.Offline>Backend</StatusBadges.Offline>;
      case "error":
        return <StatusBadges.Failure>Backend</StatusBadges.Failure>;
      default:
        return <StatusBadges.Unknown>Backend</StatusBadges.Unknown>;
    }
  };

  const getGatewayBadge = (status) => {
    switch (status) {
      case "connected":
        return <StatusBadges.Live>Gateway</StatusBadges.Live>;
      case "degraded":
        return <StatusBadges.Degraded>Gateway</StatusBadges.Degraded>;
      case "disconnected":
        return <StatusBadges.Offline>Gateway</StatusBadges.Offline>;
      case "error":
        return <StatusBadges.Failure>Gateway</StatusBadges.Failure>;
      default:
        return <StatusBadges.Unknown>Gateway</StatusBadges.Unknown>;
    }
  };

  return (
    <div className="app-shell">
      <aside className={`app-shell__sidebar ${sidebarCollapsed ? "app-shell__sidebar--collapsed" : ""}`} role="navigation" aria-label="Main navigation">
        <div className="app-shell__sidebar-header">
          {!sidebarCollapsed && (
            <div className="app-shell__logo">
              <LogoIcon />
              <span className="app-shell__logo-text">Experience Budget</span>
            </div>
          )}
          <button
            className="app-shell__collapse-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!sidebarCollapsed}
          >
            <CollapseIcon collapsed={sidebarCollapsed} />
          </button>
        </div>

        <nav className="app-shell__nav">
          <ul className="app-shell__nav-list" role="list">
            {navigation.map((item) => (
              <li key={item.path} className="app-shell__nav-item">
                <NavLink
                  to={item.path}
                  className={({ isActive }) =>
                    `app-shell__nav-link ${isActive ? "app-shell__nav-link--active" : ""}`
                  }
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <span className="app-shell__nav-icon" aria-hidden="true">
                    <item.icon />
                  </span>
                  {!sidebarCollapsed && <span className="app-shell__nav-label">{item.label}</span>}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="app-shell__sidebar-footer">
          <div className="app-shell__status-section">
            <h4 className="app-shell__status-title">System Status</h4>
            <dl className="app-shell__status-list">
              <div className="app-shell__status-row">
                <dt>Backend</dt>
                <dd>{getStatusBadge(backendStatus)}</dd>
              </div>
              <div className="app-shell__status-row">
                <dt>Gateway</dt>
                <dd>{getGatewayBadge(gatewayStatus)}</dd>
              </div>
              <div className="app-shell__status-row">
                <dt>Platform</dt>
                <dd><StatusBadge variant={platform === "checking" || platform === "unavailable" ? "unknown" : "success"} size="sm">{formatPlatform(platform)}</StatusBadge></dd>
              </div>
            </dl>
          </div>

          {!sidebarCollapsed && (
            <div className="app-shell__version">
              <span className="app-shell__version-label">Version</span>
              <span className="app-shell__version-value">0.7.0</span>
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
            <span
              className={`app-shell__data-badge app-shell__data-badge--${DEMO_MODE ? "demo" : "live"}`}
              aria-label={DEMO_MODE ? "Demo data mode" : "Live data mode"}
            >
              {DEMO_MODE ? "DEMO DATA" : "● LIVE"}
            </span>
            <button className="app-shell__header-btn" aria-label="Settings">
              <SettingsIcon />
            </button>
            <button className="app-shell__header-btn" aria-label="Notifications">
              <BellIcon />
            </button>
          </div>
        </header>

        {!DEMO_MODE && backendUnreachable && (
          <div className="app-shell__unreachable-banner" role="alert">
            ⚠ Backend unreachable — showing last known data
          </div>
        )}

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

function formatPlatform(platform) {
  if (!platform) return "Unknown";
  return platform.charAt(0).toUpperCase() + platform.slice(1);
}

function getPageTitle(pathname) {
  switch (pathname) {
    case "/compare":
      return "Network Experience Comparison";
    case "/model-intelligence":
      return "Model Intelligence";
    case "/live-control":
      return "Live Control";
    default:
      return "Experience Budget";
  }
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

function CompareIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M18 18H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2z" />
      <path d="M14 2v4" />
      <path d="M10 2v4" />
      <path d="M6 2v4" />
    </svg>
  );
}

function ModelIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8" />
      <path d="M12 17v4" />
      <path d="M6 7h12" />
      <path d="M6 11h12" />
    </svg>
  );
}

function LiveIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
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

function SettingsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

export default AppShell;
import { useState, useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import "./AppShell.css";
import { StatusBadge, StatusBadges } from "../ui/StatusBadge";

/**
 * AppShell - Main layout with sidebar navigation for three pages
 * Compare, Model Intelligence, Live Control
 */
export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [gatewayStatus, setGatewayStatus] = useState("unknown");
  const [environment, setEnvironment] = useState("detecting");

  // Check backend connectivity
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const response = await fetch("/api/v1/health");
        if (response.ok) {
          setBackendStatus("connected");
        } else {
          setBackendStatus("error");
        }
      } catch {
        setBackendStatus("disconnected");
      }
    };

    checkBackend();
    const interval = setInterval(checkBackend, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch gateway status and environment
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [capsRes, gatewayRes] = await Promise.all([
          fetch("/api/v1/system/capabilities"),
          fetch("/api/v1/gateway/status"),
        ]);

        if (capsRes.ok) {
          const caps = await capsRes.json();
          setEnvironment(caps.data?.environment || "unknown");
        }

        if (gatewayRes.ok) {
          const gateway = await gatewayRes.json();
          setGatewayStatus(gateway.data?.status || "unknown");
        }
      } catch {
        setGatewayStatus("error");
        setEnvironment("error");
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
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
      case "healthy":
        return <StatusBadges.Live>Gateway</StatusBadges.Live>;
      case "degraded":
        return <StatusBadges.Degraded>Gateway</StatusBadges.Degraded>;
      case "unavailable":
        return <StatusBadges.Offline>Gateway</StatusBadges.Offline>;
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
                <dt>Environment</dt>
                <dd>
                  <StatusBadge
                    variant={environment === "simulated_lab" ? "simulated" : environment === "production" ? "live" : "unknown"}
                    size="sm"
                  >
                    {environment.replace("_", " ")}
                  </StatusBadge>
                </dd>
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
              {getPageTitle(window.location.pathname)}
            </h1>
          </div>
          <div className="app-shell__header-right">
            <button className="app-shell__header-btn" aria-label="Settings">
              <SettingsIcon />
            </button>
            <button className="app-shell__header-btn" aria-label="Notifications">
              <BellIcon />
            </button>
          </div>
        </header>

        <main className="app-shell__content" role="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
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
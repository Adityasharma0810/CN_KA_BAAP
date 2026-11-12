import { useState, useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { HomePage } from "./pages/HomePage";
import { UsageTreePage } from "./pages/UsageTreePage";
import { LiveMetricsPage } from "./pages/LiveMetricsPage";
import { DevicesPage } from "./pages/DevicesPage";
import { IntentControlPage } from "./pages/IntentControlPage";
import { ConflictResolutionPage } from "./pages/ConflictResolutionPage";
import { NetworkHealthPage } from "./pages/NetworkHealthPage";
import { DemandForecastPage } from "./pages/DemandForecastPage";
import { MultiWANPage } from "./pages/MultiWANPage";
import { DecisionLogPage } from "./pages/DecisionLogPage";
import { ComparePage } from "./pages/ComparePage";
import { ModelIntelligencePage } from "./pages/ModelIntelligencePage";
import { SettingsPage } from "./pages/SettingsPage";
import { GatewaySetupPage } from "./pages/GatewaySetupPage";
import { SimulationPage } from "./pages/SimulationPage";
import { AboutPage } from "./pages/AboutPage";

/**
 * App - main router.
 * Public routes: /login, /register. All app routes require authentication
 * and are wrapped in AppShell. The Simulation tab is reachable without a
 * paired gateway but shows only synthetic data.
 */
function App() {
  const [token] = useState(() => sessionStorage.getItem("eb_access_token"));

  useEffect(() => {
    if (token) sessionStorage.setItem("eb_access_token", token);
    else sessionStorage.removeItem("eb_access_token");
  }, [token]);

  const isAuthenticated = !!token;

  const publicRoutes = (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<Navigate to="/login" replace />} />
      <Route
        path="/"
        element={<Navigate to="/login" replace />}
      />
    </Routes>
  );

  const appRoutes = (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/usage-tree" element={<UsageTreePage />} />
        <Route path="/live-metrics" element={<LiveMetricsPage />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="/intents" element={<IntentControlPage />} />
        <Route path="/conflicts" element={<ConflictResolutionPage />} />
        <Route path="/network-health" element={<NetworkHealthPage />} />
        <Route path="/demand-forecast" element={<DemandForecastPage />} />
        <Route path="/multi-wan" element={<MultiWANPage />} />
        <Route path="/decisions" element={<DecisionLogPage />} />
        <Route path="/experiments" element={<ComparePage />} />
        <Route path="/ml-lab" element={<ModelIntelligencePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/gateway-setup" element={<GatewaySetupPage />} />
        <Route path="/simulation" element={<SimulationPage />} />
        <Route path="/about" element={<AboutPage />} />
      </Routes>
    </AppShell>
  );

  return (
    <>
      {isAuthenticated ? appRoutes : publicRoutes}
    </>
  );
}

export default App;

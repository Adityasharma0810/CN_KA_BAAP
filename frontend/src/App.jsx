import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ComparePage } from "./pages/ComparePage";
import { ModelIntelligencePage } from "./pages/ModelIntelligencePage";
import { LiveControlPage } from "./pages/LiveControlPage";

/**
 * App - Main application router with three-page layout
 * Compare, Model Intelligence, Live Control
 */
function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/model-intelligence" element={<ModelIntelligencePage />} />
        <Route path="/live-control" element={<LiveControlPage />} />
        <Route path="/" element={<Navigate to="/compare" replace />} />
      </Routes>
    </AppShell>
  );
}

export default App;
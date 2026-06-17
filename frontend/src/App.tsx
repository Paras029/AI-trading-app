import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { DashboardPage } from "./components/dashboard/DashboardPage";
import { ScannerPage } from "./components/scanner/ScannerPage";
import { ResearchPage } from "./components/research/ResearchPage";
import { PredictionPage } from "./components/prediction/PredictionPage";
import { RiskPage } from "./components/risk/RiskPage";
import { TradesPage } from "./components/trades/TradesPage";
import { PostMortemPage } from "./components/postmortem/PostMortemPage";
import { SettingsPage } from "./components/settings/SettingsPage";
import { useWebSocket } from "./hooks/useWebSocket";

function AppContent() {
  useWebSocket("all");
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="scanner" element={<ScannerPage />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="prediction" element={<PredictionPage />} />
        <Route path="risk" element={<RiskPage />} />
        <Route path="trades" element={<TradesPage />} />
        <Route path="postmortem" element={<PostMortemPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return <AppContent />;
}

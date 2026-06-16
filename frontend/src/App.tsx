import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { OverviewPage } from "./components/overview/OverviewPage";
import { PositionsPage } from "./components/positions/PositionsPage";
import { EpisodesPage } from "./components/episodes/EpisodesPage";
import { EvolutionPage } from "./components/evolution/EvolutionPage";
import { StrategiesPage } from "./components/strategies/StrategiesPage";
import { WorldPage } from "./components/world/WorldPage";
import { LessonsPage } from "./components/lessons/LessonsPage";
import { TradesPage } from "./components/trades/TradesPage";
import { SettingsPage } from "./components/settings/SettingsPage";
import { useWebSocket } from "./hooks/useWebSocket";

function AppContent() {
  useWebSocket("all");
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="positions" element={<PositionsPage />} />
        <Route path="episodes" element={<EpisodesPage />} />
        <Route path="evolution" element={<EvolutionPage />} />
        <Route path="strategies" element={<StrategiesPage />} />
        <Route path="world" element={<WorldPage />} />
        <Route path="lessons" element={<LessonsPage />} />
        <Route path="trades" element={<TradesPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return <AppContent />;
}

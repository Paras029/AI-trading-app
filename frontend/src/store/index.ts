import { create } from "zustand";
import type {
  Portfolio,
  Trade,
  PipelineStatusCounts,
  SystemStatus,
  ScannerActivityEvent,
  ResearchActivityEvent,
  RiskActivityEvent,
  PredictionActivityEvent,
} from "../types";

interface PredictionActivityState {
  role: string;
  provider: string;
  model: string;
  status: PredictionActivityEvent["status"];
  probability?: number | null;
  reasoning?: string | null;
  market_id?: string;
}

interface AppState {
  portfolio: Portfolio | null;
  setPortfolio: (p: Portfolio | null) => void;

  pipelineStatus: PipelineStatusCounts | null;
  systemStatus: SystemStatus;
  setPipelineStatus: (p: PipelineStatusCounts, system_status: SystemStatus) => void;

  scannerLog: ScannerActivityEvent[];
  addScannerLog: (e: ScannerActivityEvent) => void;

  researchLog: ResearchActivityEvent[];
  addResearchLog: (e: ResearchActivityEvent) => void;

  riskLog: RiskActivityEvent[];
  addRiskLog: (e: RiskActivityEvent) => void;

  predictionActivity: Record<string, PredictionActivityState>;
  setPredictionActivity: (role: string, activity: PredictionActivityState) => void;

  recentTrades: Trade[];
  addTrade: (t: Trade) => void;

  notification: string | null;
  setNotification: (n: string | null) => void;
}

export const useStore = create<AppState>((set) => ({
  portfolio: null,
  setPortfolio: (p) => set({ portfolio: p }),

  pipelineStatus: null,
  systemStatus: "operational",
  setPipelineStatus: (p, system_status) => set({ pipelineStatus: p, systemStatus: system_status }),

  scannerLog: [],
  addScannerLog: (e) =>
    set((s) => ({ scannerLog: [e, ...s.scannerLog].slice(0, 50) })),

  researchLog: [],
  addResearchLog: (e) =>
    set((s) => ({ researchLog: [e, ...s.researchLog].slice(0, 50) })),

  riskLog: [],
  addRiskLog: (e) =>
    set((s) => ({ riskLog: [e, ...s.riskLog].slice(0, 50) })),

  predictionActivity: {},
  setPredictionActivity: (role, activity) =>
    set((s) => ({ predictionActivity: { ...s.predictionActivity, [role]: activity } })),

  recentTrades: [],
  addTrade: (t) =>
    set((s) => ({ recentTrades: [t, ...s.recentTrades].slice(0, 100) })),

  notification: null,
  setNotification: (n) => set({ notification: n }),
}));

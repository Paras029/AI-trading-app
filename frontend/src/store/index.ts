import { create } from "zustand";
import type { Episode, Position, AISignal, Trade, WorldContext, Market } from "../types";

interface AppState {
  activeMarket: Market;
  setActiveMarket: (m: Market) => void;

  episode: Episode | null;
  setEpisode: (e: Episode | null) => void;

  positions: Position[];
  setPositions: (p: Position[]) => void;
  updatePosition: (p: Position) => void;

  signals: AISignal[];
  addSignal: (s: AISignal) => void;

  recentTrades: Trade[];
  addTrade: (t: Trade) => void;

  world: WorldContext | null;
  setWorld: (w: WorldContext) => void;

  latestPrice: Record<string, number>;
  setPrice: (symbol: string, price: number) => void;

  notification: string | null;
  setNotification: (n: string | null) => void;
}

export const useStore = create<AppState>((set) => ({
  activeMarket: "crypto",
  setActiveMarket: (m) => set({ activeMarket: m }),

  episode: null,
  setEpisode: (e) => set({ episode: e }),

  positions: [],
  setPositions: (p) => set({ positions: p }),
  updatePosition: (p) =>
    set((s) => ({
      positions: s.positions.map((x) => (x.id === p.id ? p : x)),
    })),

  signals: [],
  addSignal: (sig) =>
    set((s) => ({ signals: [sig, ...s.signals].slice(0, 50) })),

  recentTrades: [],
  addTrade: (t) =>
    set((s) => ({ recentTrades: [t, ...s.recentTrades].slice(0, 100) })),

  world: null,
  setWorld: (w) => set({ world: w }),

  latestPrice: {},
  setPrice: (symbol, price) =>
    set((s) => ({ latestPrice: { ...s.latestPrice, [symbol]: price } })),

  notification: null,
  setNotification: (n) => set({ notification: n }),
}));

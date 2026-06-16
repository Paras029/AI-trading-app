import clsx from "clsx";
import { useStore } from "../../store";
import type { Market } from "../../types";

const MARKETS: { id: Market; label: string; icon: string }[] = [
  { id: "crypto", label: "Crypto", icon: "₿" },
  { id: "us_stocks", label: "US Stocks", icon: "📈" },
  { id: "india_stocks", label: "India", icon: "🇮🇳" },
  { id: "forex", label: "Forex", icon: "💱" },
];

export function TopBar() {
  const { activeMarket, setActiveMarket, episode } = useStore();

  return (
    <header className="h-12 bg-white border-b border-stone-200 flex items-center px-4 gap-6 shrink-0 z-10">
      {/* Logo */}
      <div className="flex items-center gap-2 shrink-0">
        <div className="w-6 h-6 rounded bg-indigo-600 flex items-center justify-center text-white text-xs font-bold">
          A
        </div>
        <span className="text-sm font-semibold text-stone-800 hidden sm:block">Apex Bot</span>
      </div>

      {/* Market tabs */}
      <nav className="flex items-center gap-1 overflow-x-auto no-scrollbar">
        {MARKETS.map((m) => (
          <button
            key={m.id}
            onClick={() => setActiveMarket(m.id)}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all",
              activeMarket === m.id
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-stone-600 hover:bg-stone-100"
            )}
          >
            <span>{m.icon}</span>
            {m.label}
          </button>
        ))}
      </nav>

      {/* Right side — equity chip */}
      {episode && (
        <div className="ml-auto shrink-0 flex items-center gap-2">
          <span className="text-xs text-stone-500 hidden sm:block">Episode {episode.generation}</span>
          <span className="text-sm font-semibold text-stone-800">
            ${episode.current_equity.toFixed(2)}
          </span>
          <span
            className={clsx(
              "text-xs font-medium px-1.5 py-0.5 rounded",
              episode.current_equity >= episode.start_equity
                ? "bg-emerald-50 text-emerald-700"
                : "bg-red-50 text-red-600"
            )}
          >
            {episode.current_equity >= episode.start_equity ? "+" : ""}
            {(((episode.current_equity - episode.start_equity) / episode.start_equity) * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </header>
  );
}

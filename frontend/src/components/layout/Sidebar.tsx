import { NavLink } from "react-router-dom";
import { LayoutDashboard, Zap, RefreshCw, TrendingUp, BookOpen, Globe, GraduationCap, ArrowLeftRight, Settings } from "lucide-react";
import { useStore } from "../../store";
import { CostWidget } from "../settings/CostWidget";
import type { Market } from "../../types";
import clsx from "clsx";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/positions", label: "Positions", icon: Zap },
  { to: "/episodes", label: "Episodes", icon: RefreshCw },
  { to: "/evolution", label: "Evolution", icon: TrendingUp },
  { to: "/strategies", label: "Strategies", icon: BookOpen },
  { to: "/world", label: "World", icon: Globe },
  { to: "/lessons", label: "Lessons", icon: GraduationCap },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/settings", label: "Settings", icon: Settings },
];

const MARKETS: { id: Market; label: string; flag: string }[] = [
  { id: "crypto", label: "Crypto", flag: "₿" },
  { id: "us_stocks", label: "US Stocks", flag: "🇺🇸" },
  { id: "india_stocks", label: "India", flag: "🇮🇳" },
  { id: "forex", label: "Forex", flag: "💱" },
];

export function Sidebar() {
  const { activeMarket, setActiveMarket, episode } = useStore();

  return (
    <aside className="w-52 min-h-screen bg-sidebar-bg border-r border-stone-200 flex flex-col py-4 px-3 shrink-0">
      {/* Profile */}
      <div className="flex items-center gap-2 mb-5 px-1">
        <div className="w-8 h-8 rounded-full bg-active-nav flex items-center justify-center text-white text-sm font-bold">
          A
        </div>
        <div>
          <p className="text-sm font-semibold text-stone-800">Apex Bot</p>
          <p className="text-xs text-stone-500">Trading Bot · v1</p>
        </div>
      </div>

      {/* Market tabs */}
      <div className="mb-4">
        <p className="text-xs text-stone-400 uppercase tracking-wider mb-2 px-1">Market</p>
        <div className="flex flex-col gap-1">
          {MARKETS.map((m) => (
            <button
              key={m.id}
              onClick={() => setActiveMarket(m.id)}
              className={clsx(
                "flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm transition-colors text-left",
                activeMarket === m.id
                  ? "bg-active-nav text-white"
                  : "text-stone-600 hover:bg-stone-200"
              )}
            >
              <span>{m.flag}</span>
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5 flex-1">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={`${to}?market=${activeMarket}`}
            end={to === "/"}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-active-nav text-white font-medium"
                  : "text-stone-600 hover:bg-stone-200"
              )
            }
          >
            <Icon size={15} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Cost widget + disclaimer */}
      <div className="mt-4 px-1">
        <CostWidget />
        <p className="text-[10px] text-stone-400 leading-relaxed">
          Simulation on real live prices. Fake money, real lessons. Honest by design — it can lose everything, it never lies.
        </p>
      </div>
    </aside>
  );
}

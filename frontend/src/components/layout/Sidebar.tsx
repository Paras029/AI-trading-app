import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Zap, RefreshCw, TrendingUp, BookOpen,
  Globe, GraduationCap, ArrowLeftRight, Settings,
} from "lucide-react";
import { useStore } from "../../store";
import { CostWidget } from "../settings/CostWidget";
import clsx from "clsx";

const MARKET_NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/positions", label: "Positions", icon: Zap },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/world", label: "World", icon: Globe },
];

const BOT_NAV = [
  { to: "/episodes", label: "Episodes", icon: RefreshCw },
  { to: "/evolution", label: "Evolution", icon: TrendingUp },
  { to: "/strategies", label: "Strategies", icon: BookOpen },
  { to: "/lessons", label: "Lessons", icon: GraduationCap },
];

function NavItem({ to, label, icon: Icon, market }: { to: string; label: string; icon: React.ElementType; market: string }) {
  return (
    <NavLink
      to={`${to}${to === "/" ? "" : ""}?market=${market}`}
      end={to === "/"}
      className={({ isActive }) =>
        clsx(
          "flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-sm transition-colors",
          isActive
            ? "bg-indigo-50 text-indigo-700 font-medium"
            : "text-stone-600 hover:bg-stone-100 hover:text-stone-800"
        )
      }
    >
      <Icon size={15} strokeWidth={1.75} />
      {label}
    </NavLink>
  );
}

export function Sidebar() {
  const { activeMarket } = useStore();

  return (
    <aside className="w-48 min-h-full bg-white border-r border-stone-200 flex flex-col py-3 px-2.5 shrink-0">
      {/* Market-specific nav */}
      <div className="mb-1">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest px-2.5 mb-1">
          Market
        </p>
        <nav className="flex flex-col gap-0.5">
          {MARKET_NAV.map(({ to, label, icon }) => (
            <NavItem key={to} to={to} label={label} icon={icon} market={activeMarket} />
          ))}
        </nav>
      </div>

      <div className="my-2 border-t border-stone-100" />

      {/* Bot-global nav */}
      <div className="mb-1">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest px-2.5 mb-1">
          Bot
        </p>
        <nav className="flex flex-col gap-0.5">
          {BOT_NAV.map(({ to, label, icon }) => (
            <NavItem key={to} to={to} label={label} icon={icon} market={activeMarket} />
          ))}
        </nav>
      </div>

      <div className="my-2 border-t border-stone-100" />

      {/* Settings */}
      <NavItem to="/settings" label="Settings" icon={Settings} market={activeMarket} />

      {/* Cost widget + disclaimer */}
      <div className="mt-auto pt-4 px-0.5">
        <CostWidget />
        <p className="text-[10px] text-stone-400 leading-relaxed mt-2">
          Simulation on real live prices. Fake money, real lessons.
        </p>
      </div>
    </aside>
  );
}

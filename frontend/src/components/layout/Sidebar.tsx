import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  LayoutDashboard, Radar, Search, BrainCircuit, ShieldCheck,
  ArrowLeftRight, GraduationCap, Settings,
} from "lucide-react";
import { CostWidget } from "../settings/CostWidget";
import type { SettingsData } from "../../types";
import clsx from "clsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/scanner", label: "Scanner", icon: Radar },
  { to: "/research", label: "Research", icon: Search },
  { to: "/prediction", label: "Prediction", icon: BrainCircuit },
  { to: "/risk", label: "Risk", icon: ShieldCheck },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/postmortem", label: "Post-Mortem", icon: GraduationCap },
];

function NavItem({ to, label, icon: Icon }: { to: string; label: string; icon: React.ElementType }) {
  return (
    <NavLink
      to={to}
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

function ModeChip() {
  const { data: settings } = useQuery<SettingsData>({
    queryKey: ["settings"],
    queryFn: () => axios.get("/api/settings").then((r) => r.data),
    refetchInterval: 10000,
  });

  const mode = settings?.config.prediction_trading_mode ?? "paper";
  const armed = settings?.config.live_armed ?? false;
  const isLive = mode === "live";

  return (
    <div
      className={clsx(
        "flex items-center justify-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded-md mb-1.5 tracking-wide",
        isLive
          ? "bg-red-50 text-red-700 border border-red-200"
          : "bg-emerald-50 text-emerald-700 border border-emerald-200"
      )}
    >
      <span className={clsx("w-1.5 h-1.5 rounded-full", isLive ? "bg-red-500" : "bg-emerald-500")} />
      {isLive ? `LIVE${armed ? " — ARMED" : ""}` : "PAPER"}
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="w-48 min-h-full bg-white border-r border-stone-200 flex flex-col py-3 px-2.5 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-2.5 mb-3">
        <div className="w-6 h-6 rounded bg-indigo-600 flex items-center justify-center text-white text-xs font-bold">
          A
        </div>
        <span className="text-sm font-semibold text-stone-800">Apex Prediction Bot</span>
      </div>

      <nav className="flex flex-col gap-0.5">
        {NAV.map(({ to, label, icon }) => (
          <NavItem key={to} to={to} label={label} icon={icon} />
        ))}
      </nav>

      <div className="my-2 border-t border-stone-100" />

      <NavItem to="/settings" label="Settings" icon={Settings} />

      {/* Mode chip + cost widget + disclaimer */}
      <div className="mt-auto pt-4 px-0.5">
        <ModeChip />
        <CostWidget />
        <p className="text-[10px] text-stone-400 leading-relaxed mt-2">
          Multi-agent Polymarket research & trading. Real prices, real or paper money.
        </p>
      </div>
    </aside>
  );
}

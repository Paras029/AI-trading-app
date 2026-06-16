import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { Episode, Position } from "../../types";
import clsx from "clsx";

interface OverviewData {
  episode: Episode | null;
  positions: Position[];
  latest_generation: number;
  notification: string | null;
  finished_episodes_count: number;
}

function fmt(n: number) {
  return n.toFixed(2);
}
function pct(n: number) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export function OverviewPage() {
  const { activeMarket } = useStore();
  const { data, isLoading } = useQuery<OverviewData>({
    queryKey: ["overview", activeMarket],
    queryFn: () => axios.get(`/api/overview?market=${activeMarket}`).then((r) => r.data),
    refetchInterval: 10000,
  });

  if (isLoading || !data) return <div className="text-stone-400">Loading...</div>;

  const ep = data.episode;
  const goalPct = ep ? (ep.current_equity / ep.goal_equity) * 100 : 0;
  const gainDollar = ep ? ep.current_equity - ep.start_equity : 0;
  const gainPct = ep ? (gainDollar / ep.start_equity) * 100 : 0;

  return (
    <div className="max-w-3xl space-y-6">
      {/* Notification banner */}
      {data.notification && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900">
          <span className="font-medium">While you were away · </span>
          {data.notification}
        </div>
      )}

      {/* Equity card */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6">
        <p className="text-sm text-stone-500 mb-1">
          Account Equity · Episode {ep?.generation ?? "—"}
        </p>
        <p className="text-4xl font-bold text-stone-900">${fmt(ep?.current_equity ?? 0)}</p>
        <div className="flex items-center gap-3 mt-1">
          <span className={clsx("font-semibold", gainDollar >= 0 ? "text-positive" : "text-negative")}>
            {gainDollar >= 0 ? "+" : ""}${fmt(Math.abs(gainDollar))}
          </span>
          <span className={clsx("text-sm px-2 py-0.5 rounded-full font-medium", gainPct >= 0 ? "bg-green-100 text-positive" : "bg-red-100 text-negative")}>
            {pct(gainPct)}
          </span>
          <span className="text-xs text-stone-400">
            this run · from ${fmt(ep?.start_equity ?? 0)}
          </span>
        </div>

        {/* Goal progress bar */}
        <div className="mt-4">
          <div className="flex justify-between text-xs text-stone-400 mb-1">
            <span>Goal · ${fmt(ep?.goal_equity ?? 500)}</span>
            <span>{goalPct.toFixed(1)}%</span>
          </div>
          <div className="h-2 bg-stone-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-active-nav rounded-full transition-all"
              style={{ width: `${Math.min(goalPct, 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Open Positions */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6">
        <h2 className="font-semibold text-stone-800 mb-4">Open Positions</h2>
        {data.positions.length === 0 ? (
          <p className="text-stone-400 text-sm">No open positions.</p>
        ) : (
          <div className="space-y-3">
            {data.positions.map((p) => (
              <PositionRow key={p.id} position={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PositionRow({ position: p }: { position: Position }) {
  const isPositive = p.unrealized_pnl >= 0;
  return (
    <div className="flex items-center justify-between py-2 border-b border-stone-50 last:border-0">
      <div className="flex items-center gap-2">
        <span className={clsx("text-xs font-bold px-1.5 py-0.5 rounded", p.side === "long" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700")}>
          {p.side.toUpperCase()}
        </span>
        <span className="font-medium text-stone-800">{p.symbol}</span>
        <span className="text-xs text-stone-400">{p.leverage}x</span>
      </div>
      <div className="text-right">
        <span className={clsx("font-semibold text-sm", isPositive ? "text-positive" : "text-negative")}>
          {isPositive ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
        </span>
        <p className="text-xs text-stone-400">{p.strategy_name}</p>
      </div>
    </div>
  );
}

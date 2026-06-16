import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { Strategy } from "../../types";
import clsx from "clsx";

const STATUS_STYLE: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  candidate: "bg-amber-100 text-amber-700",
  retired: "bg-stone-100 text-stone-400",
};

export function StrategiesPage() {
  const { activeMarket } = useStore();
  const { data = [], isLoading } = useQuery<Strategy[]>({
    queryKey: ["strategies", activeMarket],
    queryFn: () => axios.get(`/api/strategies?market=${activeMarket}`).then((r) => r.data),
    refetchInterval: 30000,
  });

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-stone-800">Strategy Book</h1>
        <p className="text-sm text-stone-400 mt-0.5">
          A strategy only earns 'active' after it proves a real edge (Exp R {">"} 0, PF {">"} 1, Sharpe {">"} 0.4). Losers get retired.
        </p>
      </div>
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm divide-y divide-stone-50">
        {data.map((s) => <StrategyRow key={s.id} strategy={s} />)}
      </div>
    </div>
  );
}

function StrategyRow({ strategy: s }: { strategy: Strategy }) {
  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-1">
        <p className="font-medium text-stone-800">{s.name}</p>
        <span className={clsx("text-xs font-semibold px-2 py-0.5 rounded-full", STATUS_STYLE[s.status])}>
          {s.status}
        </span>
      </div>
      {s.num_trades > 0 && (
        <div className="flex gap-4 text-xs text-stone-400 mt-1">
          <div><span className="text-stone-500 font-medium">Exp R</span> {s.exp_r.toFixed(2)}</div>
          <div><span className="text-stone-500 font-medium">PF</span> {s.profit_factor.toFixed(2)}</div>
          <div><span className="text-stone-500 font-medium">SR</span> {s.sharpe.toFixed(2)}</div>
          <div><span className="text-stone-500 font-medium">Win%</span> {(s.win_rate * 100).toFixed(0)}%</div>
          <div><span className="text-stone-500 font-medium">Trades</span> {s.num_trades}</div>
        </div>
      )}
      {s.num_trades === 0 && (
        <p className="text-xs text-stone-300 mt-1">No trades yet</p>
      )}
    </div>
  );
}

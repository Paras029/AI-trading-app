import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { Trade } from "../../types";
import clsx from "clsx";

export function TradesPage() {
  const { activeMarket } = useStore();
  const { data = [], isLoading } = useQuery<Trade[]>({
    queryKey: ["trades", activeMarket],
    queryFn: () => axios.get(`/api/trades?market=${activeMarket}&limit=100`).then((r) => r.data),
    refetchInterval: 10000,
  });

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold text-stone-800">Recent Fills</h1>
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm divide-y divide-stone-50">
        {data.length === 0 && (
          <p className="p-8 text-center text-stone-400">No trades yet.</p>
        )}
        {data.map((t) => <TradeRow key={t.id} trade={t} />)}
      </div>
    </div>
  );
}

function TradeRow({ trade: t }: { trade: Trade }) {
  const isOpen = t.is_open;
  const pnlColor = (t.pnl ?? 0) >= 0 ? "text-positive" : "text-negative";

  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <span className={clsx("text-[10px] font-bold px-1.5 py-0.5 rounded uppercase",
        isOpen ? "bg-blue-100 text-blue-600" : "bg-stone-100 text-stone-500"
      )}>
        {isOpen ? "open" : "close"}
      </span>
      <span className={clsx("text-xs font-bold px-1.5 py-0.5 rounded",
        t.side === "long" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      )}>
        {t.side.toUpperCase()}
      </span>
      <span className="font-medium text-stone-800 text-sm">{t.symbol}</span>
      <span className="text-xs text-stone-400">{t.leverage}x</span>
      <span className="text-xs text-stone-400 bg-stone-50 px-2 py-0.5 rounded-full flex-1 truncate">
        {t.strategy_name}
      </span>
      <span className="text-xs text-stone-400">{t.reason}</span>
      {t.pnl != null && (
        <span className={clsx("text-sm font-semibold", pnlColor)}>
          {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
        </span>
      )}
    </div>
  );
}

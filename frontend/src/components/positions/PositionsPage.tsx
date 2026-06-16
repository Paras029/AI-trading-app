import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { Position } from "../../types";
import { InfoTooltip } from "../ui/InfoTooltip";
import clsx from "clsx";

export function PositionsPage() {
  const { activeMarket } = useStore();
  const { data = [], isLoading } = useQuery<Position[]>({
    queryKey: ["positions", activeMarket],
    queryFn: () => axios.get(`/api/positions?market=${activeMarket}`).then((r) => r.data),
    refetchInterval: 5000,
  });

  if (isLoading) return <div className="text-stone-400">Loading...</div>;

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold text-stone-800">Leveraged Positions</h1>
      {data.length === 0 ? (
        <div className="bg-white rounded-2xl border border-stone-100 p-8 text-center text-stone-400">
          No open positions right now.
        </div>
      ) : (
        data.map((p) => <PositionCard key={p.id} position={p} />)
      )}
    </div>
  );
}

function PositionCard({ position: p }: { position: Position }) {
  const isPositive = p.unrealized_pnl >= 0;
  const liqWarning = p.liq_distance_pct < 10;

  return (
    <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={clsx("text-xs font-bold px-2 py-0.5 rounded", p.side === "long" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700")}>
            {p.side.toUpperCase()}
          </span>
          <span className="font-bold text-stone-900 text-lg">{p.symbol}</span>
          <span className="text-stone-400 text-sm">{p.leverage}x</span>
          <span className="text-xs text-stone-400 bg-stone-100 px-2 py-0.5 rounded-full">
            {p.strategy_name}
          </span>
        </div>
        <div className="text-right">
          <p className={clsx("font-bold text-lg", isPositive ? "text-positive" : "text-negative")}>
            {isPositive ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
          </p>
          <p className={clsx("text-sm", isPositive ? "text-positive" : "text-negative")}>
            {isPositive ? "+" : ""}{p.unrealized_pnl_pct.toFixed(2)}% ROI
          </p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 text-xs mb-3">
        <div>
          <p className="text-stone-400 flex items-center">Entry<InfoTooltip text="Price at which this position was opened." /></p>
          <p className="font-medium text-stone-700">${p.entry_price.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-stone-400 flex items-center">Mark<InfoTooltip text="Current market price. P&L is calculated against this." /></p>
          <p className="font-medium text-stone-700">${p.mark_price.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-stone-400 flex items-center">Notional<InfoTooltip text="Total position size in USD = margin × leverage. This is the actual exposure, not the capital used." /></p>
          <p className="font-medium text-stone-700">${p.notional.toFixed(0)}</p>
        </div>
        <div>
          <p className="text-stone-400 flex items-center">Liq price<InfoTooltip text="Liquidation price: if the market reaches this level, the position is automatically closed at a near-total loss. The bot monitors and closes positions well before this." /></p>
          <p className={clsx("font-medium", liqWarning ? "text-red-600" : "text-stone-700")}>${p.liquidation_price.toLocaleString()}</p>
        </div>
      </div>

      {/* Liquidation distance bar */}
      <div>
        <div className="flex justify-between text-[10px] text-stone-400 mb-1">
          <span className="flex items-center">
            Distance to liquidation
            <InfoTooltip text="How far the price needs to move before this position is liquidated. Below 10% = danger zone (bar turns red)." />
          </span>
          <span className={liqWarning ? "text-red-500 font-medium" : ""}>{p.liq_distance_pct.toFixed(1)}% away</span>
        </div>
        <div className="h-1.5 bg-stone-100 rounded-full overflow-hidden">
          <div
            className={clsx("h-full rounded-full transition-all", liqWarning ? "bg-red-400" : "bg-amber-300")}
            style={{ width: `${Math.min(p.liq_distance_pct, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

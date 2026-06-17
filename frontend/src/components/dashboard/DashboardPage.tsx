import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { DashboardData } from "../../types";
import { InfoTooltip } from "../ui/InfoTooltip";
import clsx from "clsx";

const PIPELINE_NODES: { key: keyof DashboardData["pipeline_status"]; label: string }[] = [
  { key: "scanner", label: "Scanner" },
  { key: "research", label: "Research" },
  { key: "prediction", label: "Prediction" },
  { key: "risk", label: "Risk" },
  { key: "settlement", label: "Settlement" },
];

const STATUS_STYLE: Record<string, string> = {
  operational: "bg-emerald-50 text-emerald-700 border-emerald-200",
  degraded: "bg-amber-50 text-amber-700 border-amber-200",
  paused: "bg-red-50 text-red-600 border-red-200",
};

function fmt(n: number) {
  return n.toFixed(2);
}
function pct(n: number) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export function DashboardPage() {
  const { pipelineStatus, systemStatus } = useStore();
  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ["dashboard"],
    queryFn: () => axios.get("/api/dashboard").then((r) => r.data),
    refetchInterval: 10000,
  });

  if (isLoading || !data) return <div className="text-stone-400">Loading...</div>;

  const portfolio = data.portfolio;
  const equity = portfolio?.total_equity ?? 0;
  const startBalance = portfolio?.starting_balance ?? 0;
  const gainDollar = equity - startBalance;
  const gainPct = startBalance ? (gainDollar / startBalance) * 100 : 0;
  const pipeline = pipelineStatus ?? data.pipeline_status;
  const status = pipelineStatus ? systemStatus : data.system_status;

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header + system status */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-stone-800">Dashboard</h1>
        <span
          className={clsx(
            "text-xs font-semibold px-3 py-1 rounded-full border capitalize",
            STATUS_STYLE[status] ?? STATUS_STYLE.operational
          )}
        >
          {status}
        </span>
      </div>

      {/* Equity card */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6">
        <p className="text-xs text-stone-400 mb-1 flex items-center">
          Total Equity · {portfolio?.mode === "live" ? "Live" : "Paper"}
          <InfoTooltip text="Total equity = current balance + value of open positions. Starts at the configured portfolio starting balance and is continuously updated as trades settle." />
        </p>
        <p className="text-4xl font-bold text-stone-900">${fmt(equity)}</p>
        <div className="flex items-center gap-3 mt-1">
          <span className={clsx("font-semibold", gainDollar >= 0 ? "text-positive" : "text-negative")}>
            {gainDollar >= 0 ? "+" : ""}${fmt(Math.abs(gainDollar))}
          </span>
          <span className={clsx("text-sm px-2 py-0.5 rounded-full font-medium", gainPct >= 0 ? "bg-green-100 text-positive" : "bg-red-100 text-negative")}>
            {pct(gainPct)}
          </span>
          <span className="text-xs text-stone-400">
            all-time · started at ${fmt(startBalance)}
          </span>
        </div>
        <div className="flex items-center gap-4 mt-3 text-xs text-stone-400">
          <span>Today's P&amp;L: <span className={clsx("font-semibold", data.pnl_today >= 0 ? "text-positive" : "text-negative")}>{data.pnl_today >= 0 ? "+" : ""}${fmt(data.pnl_today)}</span></span>
          <span>Peak equity: ${fmt(portfolio?.peak_equity ?? 0)}</span>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Win Rate"
          value={`${(data.win_rate * 100).toFixed(1)}%`}
          tooltip="Percentage of settled trades that resulted in a win."
        />
        <StatCard
          label="Sharpe Ratio"
          value={data.sharpe_ratio.toFixed(2)}
          tooltip="Risk-adjusted return. Higher is better; above 1.0 is generally considered good."
        />
        <StatCard
          label="Brier Score"
          value={data.brier_score.toFixed(3)}
          tooltip="Measures forecast calibration: mean squared error between predicted probability and actual outcome. Lower is better (0 = perfect, 0.25 = no skill on a 50/50 base rate)."
        />
        <StatCard
          label="Active Positions"
          value={`${data.active_positions} / ${data.position_limit}`}
          tooltip="Number of currently open trades versus the configured maximum concurrent position limit."
        />
      </div>

      {/* Pipeline status row */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6">
        <h2 className="font-semibold text-stone-800 mb-4 flex items-center">
          Pipeline Status
          <InfoTooltip text="Live count of markets currently sitting at each stage of the 5-stage pipeline: Scanner → Research → Prediction → Risk → Settlement." />
        </h2>
        <div className="flex items-center">
          {PIPELINE_NODES.map((node, i) => (
            <div key={node.key} className="flex items-center flex-1">
              <div className="flex flex-col items-center flex-1">
                <div className="w-12 h-12 rounded-full bg-indigo-50 border-2 border-indigo-200 flex items-center justify-center text-lg font-bold text-indigo-700">
                  {pipeline?.[node.key] ?? 0}
                </div>
                <p className="text-xs text-stone-500 mt-1.5">{node.label}</p>
              </div>
              {i < PIPELINE_NODES.length - 1 && (
                <div className="h-0.5 flex-1 bg-stone-100 -mt-5" />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, tooltip }: { label: string; value: string; tooltip: string }) {
  return (
    <div className="bg-white rounded-xl border border-stone-100 shadow-sm p-4">
      <p className="text-xs text-stone-400 mb-1 flex items-center">
        {label}
        <InfoTooltip text={tooltip} />
      </p>
      <p className="text-xl font-bold text-stone-900">{value}</p>
    </div>
  );
}

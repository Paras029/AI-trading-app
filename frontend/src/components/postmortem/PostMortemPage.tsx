import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { createChart, ColorType } from "lightweight-charts";
import type { PostMortem, FailureBreakdownEntry, CalibrationSnapshot } from "../../types";
import clsx from "clsx";

const FAILURE_LABELS: Record<string, string> = {
  bad_prediction: "Bad Prediction",
  bad_timing: "Bad Timing",
  external_shock: "External Shock",
  bad_execution: "Bad Execution",
  overweighted_sentiment: "Overweighted Sentiment",
  model_overconfidence: "Model Overconfidence",
};

function Sparkline({ data, color }: { data: { time: string; value: number }[]; color: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 80,
      layout: { background: { type: ColorType.Solid, color: "white" }, textColor: "#a8a29e" },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false },
      timeScale: { visible: false },
      handleScroll: false,
      handleScale: false,
    });
    const series = chart.addLineSeries({ color, lineWidth: 2 });
    series.setData(data.map((d) => ({ time: d.time as never, value: d.value })));
    chart.timeScale().fitContent();

    const onResize = () => chart.applyOptions({ width: containerRef.current?.clientWidth ?? 0 });
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, [data, color]);

  return <div ref={containerRef} className="w-full" />;
}

export function PostMortemPage() {
  const { data: postmortems = [], isLoading } = useQuery<PostMortem[]>({
    queryKey: ["postmortem"],
    queryFn: () => axios.get("/api/postmortem").then((r) => r.data),
    refetchInterval: 30000,
  });

  const { data: breakdown = [] } = useQuery<FailureBreakdownEntry[]>({
    queryKey: ["postmortem-breakdown"],
    queryFn: () => axios.get("/api/postmortem/failure-breakdown").then((r) => r.data),
    refetchInterval: 60000,
  });

  // CalibrationSnapshot history reused for performance trend sparklines
  const { data: snapshots = [] } = useQuery<CalibrationSnapshot[]>({
    queryKey: ["postmortem-snapshots"],
    queryFn: () =>
      axios.get("/api/prediction/calibration", { params: { history: true } }).then((r) =>
        Array.isArray(r.data) ? r.data : r.data?.snapshot ? [r.data.snapshot] : []
      ),
    refetchInterval: 60000,
  });

  const latest = postmortems[0];
  const maxCount = Math.max(...breakdown.map((b) => b.count), 1);

  const winRateData = snapshots
    .map((s) => ({ time: s.snapshot_at.slice(0, 10), value: s.win_rate }))
    .sort((a, b) => (a.time < b.time ? -1 : 1));
  const equityData = snapshots
    .map((s) => ({ time: s.snapshot_at.slice(0, 10), value: s.avg_pnl_per_trade }))
    .sort((a, b) => (a.time < b.time ? -1 : 1));

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-stone-800">Post-Mortem</h1>
        <p className="text-sm text-stone-400 mt-0.5">
          Every settled trade gets a review — what worked, what didn't, and why.
        </p>
      </div>

      {/* Latest trade review */}
      {isLoading ? (
        <div className="text-stone-400">Loading...</div>
      ) : !latest ? (
        <div className="bg-white rounded-2xl border border-stone-100 p-8 text-center text-stone-400">
          No post-mortems yet. Settle your first trade.
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div>
              <h3 className="font-semibold text-stone-800">{latest.lesson_title}</h3>
              <p className="text-xs text-stone-400 mt-0.5">{latest.market?.question ?? latest.market_id}</p>
            </div>
            <span
              className={clsx(
                "text-xs font-bold px-2 py-0.5 rounded-full shrink-0",
                latest.outcome === "WIN" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"
              )}
            >
              {latest.outcome}
            </span>
          </div>
          <p className="text-sm text-stone-600 leading-relaxed mb-2">{latest.analysis_text}</p>
          <p className="text-sm text-stone-700 leading-relaxed mb-3 bg-stone-50 rounded-lg p-3">
            {latest.lesson_body}
          </p>
          <div className="flex items-center gap-2 text-xs text-stone-400">
            {latest.failure_category && (
              <span className="bg-red-50 text-red-600 px-2 py-0.5 rounded">
                {FAILURE_LABELS[latest.failure_category] ?? latest.failure_category}
              </span>
            )}
            <span className="bg-stone-100 px-2 py-0.5 rounded">importance {latest.importance}</span>
            <span>·</span>
            <span>{new Date(latest.created_at).toLocaleDateString()}</span>
          </div>
        </div>
      )}

      {/* Failure category breakdown */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-stone-700 mb-3">Failure Category Breakdown</h2>
        {breakdown.length === 0 ? (
          <p className="text-stone-400 text-sm">No losing trades recorded yet.</p>
        ) : (
          <div className="space-y-2">
            {breakdown.map((b) => (
              <div key={b.failure_category} className="flex items-center gap-3">
                <span className="text-xs text-stone-600 w-44 shrink-0">
                  {FAILURE_LABELS[b.failure_category] ?? b.failure_category}
                </span>
                <div className="flex-1 h-3 bg-stone-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-red-400 rounded-full transition-all"
                    style={{ width: `${(b.count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="text-xs text-stone-500 w-16 text-right shrink-0">
                  {b.count} ({b.pct.toFixed(0)}%)
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Performance trend sparklines */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-4">
          <p className="text-xs text-stone-400 mb-1">Win Rate Trend</p>
          {winRateData.length > 1 ? (
            <Sparkline data={winRateData} color="#4F46E5" />
          ) : (
            <p className="text-stone-300 text-xs h-20 flex items-center">Not enough data yet.</p>
          )}
        </div>
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-4">
          <p className="text-xs text-stone-400 mb-1">Avg P&amp;L per Trade Trend</p>
          {equityData.length > 1 ? (
            <Sparkline data={equityData} color="#059669" />
          ) : (
            <p className="text-stone-300 text-xs h-20 flex items-center">Not enough data yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

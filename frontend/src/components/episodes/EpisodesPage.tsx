import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { Episode } from "../../types";
import clsx from "clsx";

export function EpisodesPage() {
  const { activeMarket } = useStore();
  const { data = [], isLoading } = useQuery<Episode[]>({
    queryKey: ["episodes", activeMarket],
    queryFn: () => axios.get(`/api/episodes?market=${activeMarket}`).then((r) => r.data),
    refetchInterval: 15000,
  });

  const finished = data.filter((e) => e.outcome !== "running");
  const running = data.find((e) => e.outcome === "running");

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-stone-800">Episodes</h1>
        <p className="text-sm text-stone-400 mt-0.5">
          Each run goes until it hits the goal, runs out of time, or blows up.
        </p>
      </div>

      {/* Bar chart */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
        <div className="flex items-end gap-2 h-28">
          {data.map((ep, i) => {
            const fillPct = Math.min((ep.current_equity / ep.goal_equity) * 100, 100);
            const color = ep.outcome === "goal" ? "bg-green-500" : ep.outcome === "blowup" ? "bg-red-400" : "bg-amber-400";
            return (
              <div key={ep.id} className="flex flex-col items-center gap-1 flex-1">
                <div className="w-full flex flex-col justify-end" style={{ height: "96px" }}>
                  <div className={clsx("w-full rounded-t", color)} style={{ height: `${fillPct}%`, minHeight: 4 }} />
                </div>
                <span className="text-[10px] text-stone-400">#{i + 1}</span>
              </div>
            );
          })}
          {data.length === 0 && <p className="text-stone-300 text-sm w-full text-center">No episodes yet</p>}
        </div>
      </div>

      {/* Current run */}
      {running && (
        <div className="bg-white rounded-2xl border border-amber-200 shadow-sm p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-stone-500">Current Run · Gen {running.generation}</p>
              <p className="text-2xl font-bold text-stone-900">${running.current_equity.toFixed(2)}</p>
            </div>
            <span className="text-xs bg-amber-100 text-amber-700 px-3 py-1 rounded-full font-medium">Running</span>
          </div>
        </div>
      )}

      {/* Finished runs */}
      {finished.length > 0 && (
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
          <h2 className="font-semibold text-stone-800 mb-3">Finished Runs</h2>
          <div className="space-y-2">
            {[...finished].reverse().map((ep, i) => (
              <div key={ep.id} className="flex items-center justify-between py-2 border-b border-stone-50 last:border-0">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-stone-500 font-medium">#{finished.length - i}</span>
                  <span className={clsx(
                    "text-xs font-semibold px-2 py-0.5 rounded",
                    ep.outcome === "goal" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"
                  )}>
                    {ep.outcome}
                  </span>
                </div>
                <div className="text-right text-xs text-stone-400">
                  <p>${ep.current_equity.toFixed(2)} final</p>
                  <p>{ep.num_trades} trades</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

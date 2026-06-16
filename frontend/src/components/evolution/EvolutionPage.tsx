import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { Generation } from "../../types";

export function EvolutionPage() {
  const { activeMarket } = useStore();
  const { data = [], isLoading } = useQuery<Generation[]>({
    queryKey: ["evolution", activeMarket],
    queryFn: () => axios.get(`/api/evolution?market=${activeMarket}`).then((r) => r.data),
    refetchInterval: 30000,
  });

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-stone-800">Evolution — Level-Ups</h1>
        <p className="text-sm text-stone-400 mt-0.5">
          Every finished run banks a lesson and may promote/retire a strategy, retune Kelly.
        </p>
      </div>

      {data.length === 0 ? (
        <div className="bg-white rounded-2xl border border-stone-100 p-8 text-center text-stone-400">
          No generations yet. Complete your first episode.
        </div>
      ) : (
        [...data].reverse().map((gen) => <GenCard key={gen.id} gen={gen} />)
      )}
    </div>
  );
}

function GenCard({ gen }: { gen: Generation }) {
  const promoted = gen.promoted_strategies ? gen.promoted_strategies.split(",").filter(Boolean) : [];
  const retired = gen.retired_strategies ? gen.retired_strategies.split(",").filter(Boolean) : [];

  return (
    <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-bold text-active-nav">Gen {gen.number}</span>
        <span className="text-xs text-stone-400">after episode</span>
      </div>
      <p className="text-stone-700 text-sm leading-relaxed mb-3">{gen.summary_text}</p>
      <div className="flex flex-wrap gap-3 text-xs">
        <div className="bg-stone-50 rounded-lg px-3 py-1.5">
          <span className="text-stone-400">Kelly </span>
          <span className="font-semibold text-stone-700">{(gen.kelly_fraction * 100).toFixed(0)}%</span>
        </div>
        <div className="bg-stone-50 rounded-lg px-3 py-1.5">
          <span className="text-stone-400">Max Lev </span>
          <span className="font-semibold text-stone-700">{gen.max_leverage}x</span>
        </div>
        <div className="bg-stone-50 rounded-lg px-3 py-1.5">
          <span className="text-stone-400">Lessons </span>
          <span className="font-semibold text-stone-700">{gen.lessons_count}</span>
        </div>
      </div>
      {promoted.length > 0 && (
        <p className="text-xs text-green-600 mt-2">↑ Promoted: {promoted.join(", ")}</p>
      )}
      {retired.length > 0 && (
        <p className="text-xs text-red-400 mt-1">↓ Retired: {retired.join(", ")}</p>
      )}
    </div>
  );
}

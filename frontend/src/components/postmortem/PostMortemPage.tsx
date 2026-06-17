import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { Lesson } from "../../types";
import clsx from "clsx";

const IMPORTANCE_COLOR: Record<number, string> = {
  10: "bg-red-100 text-red-700",
  9: "bg-red-50 text-red-600",
  8: "bg-orange-100 text-orange-700",
  7: "bg-amber-100 text-amber-700",
  6: "bg-yellow-50 text-yellow-700",
};

export function LessonsPage() {
  const { activeMarket } = useStore();
  const { data = [], isLoading } = useQuery<Lesson[]>({
    queryKey: ["lessons", activeMarket],
    queryFn: () => axios.get(`/api/lessons?market=${activeMarket}`).then((r) => r.data),
    refetchInterval: 30000,
  });

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-stone-800">Lessons Banked</h1>
        <p className="text-sm text-stone-400 mt-0.5">
          The bot learns harder from blow-ups than wins. Each is tagged to a market regime.
        </p>
      </div>

      {data.length === 0 ? (
        <div className="bg-white rounded-2xl border border-stone-100 p-8 text-center text-stone-400">
          No lessons yet. Complete your first episode.
        </div>
      ) : (
        data.map((l) => <LessonCard key={l.id} lesson={l} />)
      )}
    </div>
  );
}

function LessonCard({ lesson: l }: { lesson: Lesson }) {
  const impKey = Math.min(l.importance, 10) as keyof typeof IMPORTANCE_COLOR;
  const style = IMPORTANCE_COLOR[impKey] ?? "bg-stone-100 text-stone-600";

  return (
    <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="font-semibold text-stone-800">{l.title}</h3>
        <span className={clsx("text-xs font-bold px-2 py-0.5 rounded-full shrink-0", style)}>
          importance {l.importance}
        </span>
      </div>
      <p className="text-sm text-stone-600 leading-relaxed mb-2">{l.body}</p>
      <div className="flex items-center gap-2 text-xs text-stone-400">
        <span className="bg-stone-100 px-2 py-0.5 rounded">{l.market_regime}</span>
        <span>·</span>
        <span>{new Date(l.created_at).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

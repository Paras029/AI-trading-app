import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface CostsData {
  total_usd: number;
}

interface SettingsData {
  config: { signal_model: string; prompt_depth: string };
  available_models: { id: string; name: string }[];
}

function shortModelName(id: string): string {
  if (id.includes("haiku")) return "Haiku";
  if (id.includes("sonnet")) return "Sonnet";
  if (id.includes("opus")) return "Opus";
  return id.split("-")[1] ?? id;
}

export function CostWidget() {
  const { data: costs } = useQuery<CostsData>({
    queryKey: ["costs", "today"],
    queryFn: () => axios.get("/api/costs?period=today").then((r) => r.data),
    refetchInterval: 30000,
  });

  const { data: settings } = useQuery<SettingsData>({
    queryKey: ["settings"],
    queryFn: () => axios.get("/api/settings").then((r) => r.data),
    refetchInterval: 60000,
  });

  const totalUsd = costs?.total_usd ?? 0;
  const model = settings?.config.signal_model ?? "";

  return (
    <div className="flex items-center justify-between text-[10px] text-stone-500 px-1 py-1 bg-stone-100 rounded-md mb-2">
      <span className="font-medium text-stone-700">${totalUsd.toFixed(3)}</span>
      <span className="text-stone-400">today</span>
      {model && (
        <span className="bg-stone-200 text-stone-600 rounded px-1 py-0.5 font-mono">
          {shortModelName(model)}
        </span>
      )}
    </div>
  );
}

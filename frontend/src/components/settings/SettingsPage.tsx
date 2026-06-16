import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import clsx from "clsx";

interface Model {
  id: string;
  name: string;
  tier: string;
  input_cost_per_m: number;
  output_cost_per_m: number;
  description: string;
}

interface DepthOption {
  id: string;
  label: string;
  description: string;
  candles: number;
  headlines: number;
  knowledge: number;
  max_tokens: number;
}

interface BotConfig {
  signal_model: string;
  prompt_depth: string;
}

interface SettingsData {
  config: BotConfig;
  available_models: Model[];
  prompt_depths: DepthOption[];
}

interface CostEntry {
  model?: string;
  call_type?: string;
  market?: string;
  cost_usd: number;
  calls: number;
}

interface CostsData {
  period: string;
  total_usd: number;
  total_calls: number;
  by_model: CostEntry[];
  by_call_type: CostEntry[];
  by_market: CostEntry[];
}

type Period = "today" | "week" | "all";

function fmt(n: number) {
  return n < 0.001 ? "<$0.001" : `$${n.toFixed(4)}`;
}

export function SettingsPage() {
  const qc = useQueryClient();
  const [period, setPeriod] = useState<Period>("today");

  const { data: settings, isLoading } = useQuery<SettingsData>({
    queryKey: ["settings"],
    queryFn: () => axios.get("/api/settings").then((r) => r.data),
  });

  const { data: costs, isLoading: costsLoading } = useQuery<CostsData>({
    queryKey: ["costs", period],
    queryFn: () => axios.get(`/api/costs?period=${period}`).then((r) => r.data),
    refetchInterval: 30000,
  });

  const mutation = useMutation({
    mutationFn: (patch: Partial<BotConfig>) =>
      axios.put("/api/settings", patch).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  if (isLoading || !settings) {
    return <div className="text-stone-400 p-6">Loading settings…</div>;
  }

  const { config, available_models, prompt_depths } = settings;

  return (
    <div className="p-6 max-w-2xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-stone-800 mb-1">Settings</h1>
        <p className="text-sm text-stone-500">
          Changes apply immediately — no restart needed.
        </p>
      </div>

      {/* ── Signal Model ─────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Signal Model
        </h2>
        <div className="space-y-2">
          {available_models.map((m) => (
            <button
              key={m.id}
              onClick={() => mutation.mutate({ signal_model: m.id })}
              className={clsx(
                "w-full text-left border rounded-lg p-3 transition-all",
                config.signal_model === m.id
                  ? "border-active-nav bg-blue-50"
                  : "border-stone-200 hover:border-stone-300 bg-white"
              )}
            >
              <div className="flex items-center justify-between mb-0.5">
                <span className="font-medium text-sm text-stone-800">{m.name}</span>
                <span className="text-xs text-stone-400">
                  ${m.input_cost_per_m}/M in · ${m.output_cost_per_m}/M out
                </span>
              </div>
              <p className="text-xs text-stone-500">{m.description}</p>
            </button>
          ))}
        </div>
        {mutation.isPending && (
          <p className="text-xs text-stone-400 mt-1">Saving…</p>
        )}
      </section>

      {/* ── Prompt Depth ─────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Prompt Depth
        </h2>
        <div className="grid grid-cols-3 gap-2">
          {prompt_depths.map((d) => (
            <button
              key={d.id}
              onClick={() => mutation.mutate({ prompt_depth: d.id })}
              className={clsx(
                "border rounded-lg p-3 text-left transition-all",
                config.prompt_depth === d.id
                  ? "border-active-nav bg-blue-50"
                  : "border-stone-200 hover:border-stone-300 bg-white"
              )}
            >
              <p className="font-medium text-sm text-stone-800 mb-1">{d.label}</p>
              <p className="text-xs text-stone-500 leading-relaxed">{d.description}</p>
              <p className="text-xs text-stone-400 mt-1.5">
                {d.candles}c · {d.headlines}h · {d.max_tokens}tok
              </p>
            </button>
          ))}
        </div>
      </section>

      {/* ── API Cost Breakdown ───────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider">
            API Cost
          </h2>
          <div className="flex gap-1">
            {(["today", "week", "all"] as Period[]).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={clsx(
                  "px-2.5 py-0.5 rounded text-xs font-medium transition-colors",
                  period === p
                    ? "bg-active-nav text-white"
                    : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                )}
              >
                {p === "today" ? "24h" : p === "week" ? "7d" : "All"}
              </button>
            ))}
          </div>
        </div>

        {costsLoading ? (
          <div className="text-stone-400 text-sm">Loading…</div>
        ) : costs ? (
          <div className="space-y-4">
            <div className="bg-stone-50 rounded-lg p-4 flex items-center justify-between">
              <div>
                <p className="text-2xl font-semibold text-stone-800">
                  {fmt(costs.total_usd)}
                </p>
                <p className="text-xs text-stone-500">{costs.total_calls} API calls</p>
              </div>
              <p className="text-xs text-stone-400 capitalize">{period} period</p>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <CostTable title="By Model" rows={costs.by_model} keyField="model" />
              <CostTable title="By Type" rows={costs.by_call_type} keyField="call_type" />
              <CostTable title="By Market" rows={costs.by_market} keyField="market" />
            </div>
          </div>
        ) : (
          <div className="text-stone-400 text-sm">No cost data yet.</div>
        )}
      </section>
    </div>
  );
}

function CostTable({
  title,
  rows,
  keyField,
}: {
  title: string;
  rows: CostEntry[];
  keyField: "model" | "call_type" | "market";
}) {
  return (
    <div className="bg-white border border-stone-200 rounded-lg p-3">
      <p className="text-xs font-semibold text-stone-600 uppercase tracking-wider mb-2">
        {title}
      </p>
      {rows.length === 0 ? (
        <p className="text-xs text-stone-400">None yet.</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((r, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-stone-600 truncate max-w-[60%]">
                {(r[keyField] ?? "—").split("-").slice(0, 2).join("-")}
              </span>
              <span className="text-stone-800 font-medium">{fmt(r.cost_usd)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

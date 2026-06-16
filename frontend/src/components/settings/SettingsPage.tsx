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

interface BotStatus {
  paused: boolean;
  market_hours: Record<string, boolean>;
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

const MARKET_LABELS: Record<string, string> = {
  crypto: "Crypto",
  us_stocks: "US Stocks",
  india_stocks: "India",
  forex: "Forex",
};

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

  const { data: status, refetch: refetchStatus } = useQuery<BotStatus>({
    queryKey: ["bot-status"],
    queryFn: () => axios.get("/api/settings/status").then((r) => r.data),
    refetchInterval: 10000,
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

  const pauseMutation = useMutation({
    mutationFn: (paused: boolean) =>
      axios.post(`/api/settings/${paused ? "pause" : "resume"}`).then((r) => r.data),
    onSuccess: () => {
      refetchStatus();
    },
  });

  if (isLoading || !settings) {
    return <div className="text-stone-400 p-6">Loading settings…</div>;
  }

  const { config, available_models, prompt_depths } = settings;
  const paused = status?.paused ?? false;
  const market_hours = status?.market_hours ?? {};

  return (
    <div className="p-6 max-w-2xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-stone-800 mb-1">Settings</h1>
        <p className="text-sm text-stone-500">
          Changes apply immediately — no restart needed.
        </p>
      </div>

      {/* ── Trading Controls ─────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Trading Controls
        </h2>
        <div className="border rounded-lg p-4 bg-white space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className={clsx(
                  "inline-block w-2 h-2 rounded-full",
                  paused ? "bg-red-500" : "bg-green-500"
                )}
              />
              <span className="text-sm font-medium text-stone-800">
                {paused ? "Bot Paused" : "Bot Running"}
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => pauseMutation.mutate(true)}
                disabled={paused || pauseMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Pause All Trading
              </button>
              <button
                onClick={() => pauseMutation.mutate(false)}
                disabled={!paused || pauseMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium rounded border border-green-300 text-green-700 hover:bg-green-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Resume Trading
              </button>
            </div>
          </div>
          <p className="text-xs text-stone-500">
            Pause stops new signals. Stop-loss and take-profit monitoring keeps running.
          </p>
          {Object.keys(MARKET_LABELS).length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {Object.entries(MARKET_LABELS).map(([key, label]) => {
                const open = market_hours[key];
                return (
                  <span
                    key={key}
                    className={clsx(
                      "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs",
                      open
                        ? "bg-green-50 text-green-700 border border-green-200"
                        : "bg-stone-100 text-stone-500 border border-stone-200"
                    )}
                  >
                    <span className={clsx("w-1.5 h-1.5 rounded-full", open ? "bg-green-500" : "bg-stone-400")} />
                    {label}
                  </span>
                );
              })}
            </div>
          )}
        </div>
      </section>

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

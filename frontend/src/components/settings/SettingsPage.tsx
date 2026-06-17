import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import clsx from "clsx";
import type { SettingsData, BotConfig, BotStatus, Mode } from "../../types";
import { ConfirmPhraseInput } from "../ui/ConfirmPhraseInput";

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

const ARM_PHRASE = "I UNDERSTAND THE RISK";

function fmt(n: number) {
  return n < 0.001 ? "<$0.001" : `$${n.toFixed(4)}`;
}

export function SettingsPage() {
  const qc = useQueryClient();
  const [period, setPeriod] = useState<Period>("today");
  const [localGates, setLocalGates] = useState<Partial<BotConfig> | null>(null);

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

  useEffect(() => {
    if (settings && !localGates) setLocalGates(settings.config);
  }, [settings, localGates]);

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

  const armMutation = useMutation({
    mutationFn: (confirmation: string) =>
      axios.post("/api/settings/arm-live", { confirmation }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const disarmMutation = useMutation({
    mutationFn: () => axios.post("/api/settings/disarm-live").then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  const startMutation = useMutation({
    mutationFn: () => axios.post("/api/settings/start").then((r) => r.data),
    onSuccess: () => refetchStatus(),
  });

  const stopMutation = useMutation({
    mutationFn: () => axios.post("/api/settings/stop").then((r) => r.data),
    onSuccess: () => refetchStatus(),
  });

  if (isLoading || !settings || !localGates) {
    return <div className="text-stone-400 p-6">Loading settings…</div>;
  }

  const { config, forecast_roles, forecast_models } = settings;
  const totalWeight = forecast_roles.reduce(
    (sum, r) => sum + (config.forecast_role_weights?.[r.role] ?? r.default_weight),
    0
  ) || 1;
  const paused = status?.paused ?? false;
  const running = status?.running ?? false;
  const mode = config.prediction_trading_mode;
  const armed = config.live_armed;

  function saveGateField(key: keyof BotConfig, value: number) {
    setLocalGates((g) => (g ? { ...g, [key]: value } : g));
  }

  const GATE_FIELDS: { key: keyof BotConfig; label: string; step: number }[] = [
    { key: "min_edge_pct", label: "Min Edge %", step: 0.01 },
    { key: "max_position_pct", label: "Max Position %", step: 0.01 },
    { key: "single_position_cap_usd", label: "Single Position Cap ($)", step: 1 },
    { key: "max_total_exposure_pct", label: "Max Total Exposure %", step: 0.01 },
    { key: "max_concurrent_positions", label: "Max Concurrent Positions", step: 1 },
    { key: "max_drawdown_pct", label: "Max Drawdown %", step: 0.01 },
    { key: "daily_loss_limit_pct", label: "Daily Loss Limit %", step: 0.01 },
    { key: "max_slippage_pct", label: "Max Slippage %", step: 0.01 },
  ];

  return (
    <div className="p-6 max-w-2xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-stone-800 mb-1">Settings</h1>
        <p className="text-sm text-stone-500">
          Changes apply immediately — no restart needed.
        </p>
      </div>

      {/* ── Bot Lifecycle ─────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Bot Lifecycle
        </h2>
        <div className="border rounded-lg p-4 bg-white space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className={clsx(
                  "inline-block w-2 h-2 rounded-full",
                  running ? "bg-green-500" : "bg-stone-400"
                )}
              />
              <span className="text-sm font-medium text-stone-800">
                {running ? "Bot Started" : "Bot Stopped"}
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => startMutation.mutate()}
                disabled={running || startMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium rounded border border-green-300 text-green-700 hover:bg-green-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Start Bot
              </button>
              <button
                onClick={() => stopMutation.mutate()}
                disabled={!running || stopMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Stop Bot
              </button>
            </div>
          </div>
          <p className="text-xs text-stone-500">
            The pipeline never auto-starts on boot — start it here. Stopping cancels the
            scanner/research/prediction/risk/settlement loops; it does not close any open
            trades. Close positions from the Trades page.
          </p>
        </div>
      </section>

      {/* ── Trade Gating ──────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Trade Gating
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
                disabled={!running || paused || pauseMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Pause All Trading
              </button>
              <button
                onClick={() => pauseMutation.mutate(false)}
                disabled={!running || !paused || pauseMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium rounded border border-green-300 text-green-700 hover:bg-green-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Resume Trading
              </button>
            </div>
          </div>
          <p className="text-xs text-stone-500">
            Pause stops new risk-approved trades. Scanner/Research/Prediction keep running so the UI stays informative; the kill switch (gate 1 of 9) short-circuits the Risk stage. Disabled while the bot is stopped.
          </p>
        </div>
      </section>

      {/* ── Execution Mode + Arm Live ───────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Execution Mode
        </h2>
        <div className="flex gap-2 mb-3">
          <button
            onClick={() => mutation.mutate({ prediction_trading_mode: "paper" as Mode })}
            className={clsx(
              "flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors",
              mode === "paper" ? "bg-emerald-50 border-emerald-300 text-emerald-700" : "border-stone-200 text-stone-500 hover:border-stone-300"
            )}
          >
            Paper
          </button>
          <button
            onClick={() => mutation.mutate({ prediction_trading_mode: "live" as Mode })}
            className={clsx(
              "flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors",
              mode === "live" ? "bg-red-50 border-red-300 text-red-700" : "border-stone-200 text-stone-500 hover:border-stone-300"
            )}
          >
            Live
          </button>
        </div>

        <div className="border-2 border-red-300 rounded-xl p-4 bg-red-50/40 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-red-700">Arm Live Trading</p>
            <span
              className={clsx(
                "text-[10px] font-bold px-2 py-0.5 rounded-full uppercase",
                armed ? "bg-red-600 text-white" : "bg-stone-200 text-stone-500"
              )}
            >
              {armed ? "armed" : "disarmed"}
            </span>
          </div>
          <p className="text-xs text-red-700/80 leading-relaxed">
            Full gate grid and live decision log live on the Risk page. Type the exact phrase
            below to arm — real funds will be used once "Live" mode and "Armed" are both active.
          </p>
          <ConfirmPhraseInput
            phrase={ARM_PHRASE}
            onConfirm={() => armMutation.mutate(ARM_PHRASE)}
            disabled={armed}
            pending={armMutation.isPending}
            buttonLabel="Arm Live Trading"
          />
          <button
            onClick={() => disarmMutation.mutate()}
            disabled={!armed || disarmMutation.isPending}
            className="w-full px-3 py-2 rounded-lg text-sm font-medium border border-stone-300 text-stone-700 hover:bg-stone-50 disabled:opacity-40 transition-colors"
          >
            Disarm
          </button>
        </div>
      </section>

      {/* ── Forecast Roles ─────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-1">
          Forecast Roles
        </h2>
        <p className="text-xs text-stone-500 mb-3">
          Assign any available model to each role. Models without a configured API key are
          greyed out — give me the keys you have and only those show up as selectable.
        </p>
        <div className="space-y-2">
          {forecast_roles.map((r) => {
            const weight = config.forecast_role_weights?.[r.role] ?? r.default_weight;
            const modelId = config.forecast_role_models?.[r.role] ?? r.default_model;
            const selectedModel = forecast_models.find((m) => m.id === modelId);
            const normalizedPct = (weight / totalWeight) * 100;
            return (
              <div key={r.role} className="border border-stone-200 rounded-lg p-3 bg-white">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm text-stone-800 capitalize">{r.role.replace(/_/g, " ")}</span>
                  <span
                    className={clsx(
                      "text-[10px] font-bold px-1.5 py-0.5 rounded uppercase",
                      selectedModel?.has_key
                        ? "bg-emerald-50 text-emerald-600"
                        : "bg-red-50 text-red-500"
                    )}
                  >
                    {selectedModel ? `${selectedModel.provider}${selectedModel.has_key ? "" : " — no key"}` : "unassigned"}
                  </span>
                </div>

                <select
                  value={modelId}
                  onChange={(e) =>
                    mutation.mutate({
                      forecast_role_models: { ...config.forecast_role_models, [r.role]: e.target.value },
                    })
                  }
                  className="w-full border border-stone-200 rounded px-2 py-1.5 text-xs mb-2 bg-white"
                >
                  {forecast_models.map((m) => (
                    <option key={m.id} value={m.id} disabled={!m.has_key}>
                      {m.label} ({m.provider} · {m.tier}){m.has_key ? "" : " — no API key"}
                    </option>
                  ))}
                </select>

                <label className="block">
                  <span className="text-[11px] text-stone-400 mb-1 flex justify-between">
                    <span>Weight</span>
                    <span className="font-medium text-stone-700">
                      {weight.toFixed(2)} raw · {normalizedPct.toFixed(0)}% of ensemble
                    </span>
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={weight}
                    onChange={(e) =>
                      mutation.mutate({
                        forecast_role_weights: { ...config.forecast_role_weights, [r.role]: Number(e.target.value) },
                      })
                    }
                    className="w-full"
                  />
                </label>
              </div>
            );
          })}
        </div>
        <p className="text-[11px] text-stone-400 mt-2">
          Roles whose assigned model has no API key are skipped at run time (zero cost) and the
          remaining roles' weights are renormalized to sum to 100% automatically.
        </p>
      </section>

      {/* ── Scanner Filter Defaults ─────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Scanner Filter Defaults
        </h2>
        <div className="grid grid-cols-3 gap-3">
          <NumberField label="Min Volume ($)" value={config.scanner_min_volume} onChange={(v) => mutation.mutate({ scanner_min_volume: v })} />
          <NumberField label="Max Expiry (days)" value={config.scanner_max_expiry_days} onChange={(v) => mutation.mutate({ scanner_max_expiry_days: v })} />
          <NumberField label="Min Edge (%)" value={config.scanner_min_edge_pct} step={0.01} onChange={(v) => mutation.mutate({ scanner_min_edge_pct: v })} />
        </div>
      </section>

      {/* ── Risk Gate Thresholds ─────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider mb-3">
          Risk Gate Thresholds
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {GATE_FIELDS.map((f) => (
            <NumberField
              key={f.key}
              label={f.label}
              step={f.step}
              value={Number(localGates[f.key] ?? 0)}
              onChange={(v) => saveGateField(f.key, v)}
              onBlurCommit={() => mutation.mutate({ [f.key]: localGates[f.key] } as Partial<BotConfig>)}
            />
          ))}
        </div>

        <div className="mt-4">
          <label className="block">
            <span className="text-xs text-stone-400 mb-1 flex justify-between">
              <span>Kelly Multiplier</span>
              <span className="font-medium text-stone-700">{((localGates.kelly_multiplier ?? config.kelly_multiplier) * 100).toFixed(0)}%</span>
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={localGates.kelly_multiplier ?? config.kelly_multiplier}
              onChange={(e) => saveGateField("kelly_multiplier", Number(e.target.value))}
              onMouseUp={() => mutation.mutate({ kelly_multiplier: localGates.kelly_multiplier })}
              onTouchEnd={() => mutation.mutate({ kelly_multiplier: localGates.kelly_multiplier })}
              className="w-full"
            />
            <span className="text-[11px] text-stone-400 mt-1 block">
              Fraction of full Kelly stake actually applied (e.g. 25% = quarter-Kelly).
            </span>
          </label>
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

function NumberField({
  label,
  value,
  onChange,
  onBlurCommit,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  onBlurCommit?: () => void;
  step?: number;
}) {
  return (
    <label className="block">
      <span className="text-xs text-stone-400 mb-1 block">{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        onBlur={onBlurCommit}
        className="w-full border border-stone-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200"
      />
    </label>
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

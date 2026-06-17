import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { RiskDecision, RiskGateCheck, SettingsData, Mode } from "../../types";
import { InfoTooltip } from "../ui/InfoTooltip";
import clsx from "clsx";

const ARM_PHRASE = "I UNDERSTAND THE RISK";

const GATE_LABELS: Record<string, string> = {
  kill_switch: "Kill Switch",
  edge_threshold: "Edge Threshold",
  position_size_pct: "Position Size %",
  single_position_cap: "Single Position Cap",
  total_exposure_pct: "Total Exposure %",
  position_count: "Position Count",
  max_drawdown: "Max Drawdown",
  daily_loss_limit: "Daily Loss Limit",
  slippage_check: "Slippage Check",
};

function GateCell({ gate }: { gate: RiskGateCheck }) {
  const style =
    gate.passed === true
      ? "bg-emerald-50 border-emerald-200 text-emerald-700"
      : gate.passed === false
      ? "bg-red-50 border-red-200 text-red-700"
      : "bg-stone-50 border-stone-200 text-stone-400";

  return (
    <div className={clsx("rounded-lg border p-3", style)}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold">{GATE_LABELS[gate.gate_name] ?? gate.gate_name}</span>
        <span className="text-[10px] font-bold uppercase">
          {gate.passed === true ? "pass" : gate.passed === false ? "fail" : "skipped"}
        </span>
      </div>
      {gate.threshold_value != null && gate.actual_value != null && (
        <p className="text-[11px] opacity-80">
          {gate.actual_value.toFixed(3)} vs {gate.threshold_value.toFixed(3)}
        </p>
      )}
      {gate.detail && <p className="text-[11px] opacity-70 mt-0.5">{gate.detail}</p>}
    </div>
  );
}

function ArmLiveControl() {
  const qc = useQueryClient();
  const [confirmText, setConfirmText] = useState("");

  const { data: settings } = useQuery<SettingsData>({
    queryKey: ["settings"],
    queryFn: () => axios.get("/api/settings").then((r) => r.data),
  });

  const modeMutation = useMutation({
    mutationFn: (mode: Mode) =>
      axios.put("/api/settings", { prediction_trading_mode: mode }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  const armMutation = useMutation({
    mutationFn: (confirmation: string) =>
      axios.post("/api/settings/arm-live", { confirmation }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setConfirmText("");
    },
  });

  const disarmMutation = useMutation({
    mutationFn: () => axios.post("/api/settings/disarm-live").then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  const mode = settings?.config.prediction_trading_mode ?? "paper";
  const armed = settings?.config.live_armed ?? false;
  const phraseMatches = confirmText === ARM_PHRASE;

  return (
    <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5 space-y-4">
      <h2 className="text-sm font-semibold text-stone-700">Execution Mode</h2>
      <div className="flex gap-2">
        <button
          onClick={() => modeMutation.mutate("paper")}
          className={clsx(
            "flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors",
            mode === "paper" ? "bg-emerald-50 border-emerald-300 text-emerald-700" : "border-stone-200 text-stone-500 hover:border-stone-300"
          )}
        >
          Paper
        </button>
        <button
          onClick={() => modeMutation.mutate("live")}
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
          Real funds will be used to place orders on Polymarket once both "Live" mode and "Armed"
          are active. Type the exact phrase below to enable arming.
        </p>
        <p className="text-xs font-mono bg-white border border-red-200 rounded px-2 py-1 text-red-800">
          {ARM_PHRASE}
        </p>
        <input
          type="text"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="Type confirmation phrase"
          disabled={armed}
          className="w-full border border-red-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-200 disabled:opacity-50"
        />
        <div className="flex gap-2">
          <button
            onClick={() => armMutation.mutate(confirmText)}
            disabled={!phraseMatches || armed || armMutation.isPending}
            className="flex-1 px-3 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Arm Live Trading
          </button>
          <button
            onClick={() => disarmMutation.mutate()}
            disabled={!armed || disarmMutation.isPending}
            className="flex-1 px-3 py-2 rounded-lg text-sm font-medium border border-stone-300 text-stone-700 hover:bg-stone-50 disabled:opacity-40 transition-colors"
          >
            Disarm
          </button>
        </div>
      </div>
    </div>
  );
}

export function RiskPage() {
  const { riskLog } = useStore();
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);

  const { data: decisions = [], isLoading } = useQuery<RiskDecision[]>({
    queryKey: ["risk-decisions"],
    queryFn: () => axios.get("/api/risk/recent-decisions").then((r) => r.data),
    refetchInterval: 15000,
  });

  useEffect(() => {
    if (!selectedSignalId && decisions.length > 0) setSelectedSignalId(decisions[0].signal_id);
  }, [decisions, selectedSignalId]);

  const { data: gates = [] } = useQuery<RiskGateCheck[]>({
    queryKey: ["risk-checks", selectedSignalId],
    queryFn: () => axios.get(`/api/risk/checks/${selectedSignalId}`).then((r) => r.data),
    enabled: !!selectedSignalId,
  });

  const selectedDecision = decisions.find((d) => d.signal_id === selectedSignalId) ?? null;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-stone-800">Risk &amp; Execution</h1>
        <p className="text-sm text-stone-400 mt-0.5">9 fixed-order gates, Kelly sizing, and the live-trading arm switch.</p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-6">
          {/* Decision selector */}
          <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-4">
            {isLoading ? (
              <p className="text-stone-400 text-sm">Loading…</p>
            ) : decisions.length === 0 ? (
              <p className="text-stone-400 text-sm">No risk decisions yet.</p>
            ) : (
              <div className="flex gap-2 overflow-x-auto">
                {decisions.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setSelectedSignalId(d.signal_id)}
                    className={clsx(
                      "px-3 py-2 rounded-lg text-xs text-left shrink-0 border transition-colors",
                      selectedSignalId === d.signal_id ? "border-indigo-300 bg-indigo-50" : "border-stone-200 hover:border-stone-300"
                    )}
                  >
                    <p className="font-medium text-stone-700 truncate max-w-[160px]">
                      {d.market?.question ?? d.signal_id}
                    </p>
                    <p className={clsx("mt-0.5 font-semibold", d.approved ? "text-emerald-600" : "text-red-500")}>
                      {d.approved ? "APPROVED" : "REJECTED"}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Trade proposal card */}
          {selectedDecision && (
            <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-stone-700">Trade Proposal</h2>
                <span
                  className={clsx(
                    "text-xs font-bold px-3 py-1 rounded-full",
                    selectedDecision.approved ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"
                  )}
                >
                  {selectedDecision.approved ? "APPROVED" : "REJECTED"}
                </span>
              </div>

              {/* Kelly panel */}
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div>
                  <p className="text-xs text-stone-400 flex items-center">
                    Full Kelly %
                    <InfoTooltip text="The full Kelly criterion fraction of bankroll this bet would warrant, before any safety multiplier." />
                  </p>
                  <p className="text-lg font-bold text-stone-800">{(selectedDecision.kelly_fraction_full * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-xs text-stone-400 flex items-center">
                    Applied Stake
                    <InfoTooltip text="Actual dollar amount staked, after applying the Kelly multiplier and single-position cap." />
                  </p>
                  <p className="text-lg font-bold text-stone-800">${selectedDecision.stake_usdc.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-stone-400 flex items-center">
                    Execution Status
                    <InfoTooltip text="Whether this approved trade has been filled (paper or live)." />
                  </p>
                  <p className="text-lg font-bold text-stone-800">{selectedDecision.trade_id ? "Filled" : "Pending"}</p>
                </div>
              </div>

              {/* 9-gate grid */}
              <div className="grid grid-cols-3 gap-2">
                {gates.map((g) => <GateCell key={g.id} gate={g} />)}
                {gates.length === 0 && <p className="text-stone-400 text-sm col-span-3">No gate checks recorded.</p>}
              </div>
            </div>
          )}

          {/* Live gate log */}
          <div className="bg-white rounded-2xl border border-stone-100 shadow-sm">
            <h2 className="text-sm font-semibold text-stone-700 px-5 pt-5 pb-3">Live Gate Evaluation Log</h2>
            <div className="divide-y divide-stone-50 max-h-64 overflow-auto font-mono text-xs">
              {riskLog.length === 0 && (
                <p className="p-5 text-stone-400 text-sm font-sans">Waiting for risk activity…</p>
              )}
              {riskLog.map((e, i) => (
                <div key={i} className="px-4 py-2 text-stone-600 leading-relaxed">
                  <span className="text-stone-300 mr-2">{new Date(e.ts).toLocaleTimeString()}</span>
                  <span className={clsx("mr-1 font-bold", e.passed ? "text-emerald-600" : "text-red-500")}>
                    [{e.sequence}/9]
                  </span>
                  {GATE_LABELS[e.gate_name] ?? e.gate_name}
                  {e.detail ? ` — ${e.detail}` : ""}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Arm-live control */}
        <ArmLiveControl />
      </div>
    </div>
  );
}

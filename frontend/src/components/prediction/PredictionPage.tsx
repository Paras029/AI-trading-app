import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { PredictionSignal, ModelForecast, CalibrationData, ForecastStatus } from "../../types";
import { InfoTooltip } from "../ui/InfoTooltip";
import clsx from "clsx";

const ROLE_LABELS: Record<string, string> = {
  primary_forecaster: "Primary Forecaster",
  news_analyst: "News Analyst",
  bull_advocate: "Bull Advocate",
  bear_advocate: "Bear Advocate",
  risk_contrarian: "Risk Contrarian",
};

const ROLE_ORDER = ["primary_forecaster", "news_analyst", "bull_advocate", "bear_advocate", "risk_contrarian"];

const STATUS_STYLE: Record<ForecastStatus, string> = {
  ok: "bg-emerald-50 text-emerald-700 border-emerald-200",
  thinking: "bg-amber-50 text-amber-700 border-amber-200 animate-pulse",
  skipped_no_key: "bg-stone-100 text-stone-400 border-stone-200",
  error: "bg-red-50 text-red-600 border-red-200",
  timeout: "bg-red-50 text-red-600 border-red-200",
};

const STATUS_LABEL: Record<ForecastStatus, string> = {
  ok: "Done",
  thinking: "Thinking…",
  skipped_no_key: "No API Key",
  error: "Error",
  timeout: "Timeout",
};

export function PredictionPage() {
  const { predictionActivity } = useStore();
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);

  const { data: signals = [], isLoading } = useQuery<PredictionSignal[]>({
    queryKey: ["prediction-signals"],
    queryFn: () => axios.get("/api/prediction/signals").then((r) => r.data),
    refetchInterval: 15000,
  });

  useEffect(() => {
    if (!selectedSignalId && signals.length > 0) setSelectedSignalId(signals[0].id);
  }, [signals, selectedSignalId]);

  const { data: forecasts = [] } = useQuery<ModelForecast[]>({
    queryKey: ["prediction-forecasts", selectedSignalId],
    queryFn: () =>
      axios.get(`/api/prediction/signals/${selectedSignalId}/forecasts`).then((r) => r.data),
    enabled: !!selectedSignalId,
  });

  const { data: calibration } = useQuery<CalibrationData>({
    queryKey: ["prediction-calibration"],
    queryFn: () => axios.get("/api/prediction/calibration").then((r) => r.data),
    refetchInterval: 30000,
  });

  const selectedSignal = signals.find((s) => s.id === selectedSignalId) ?? null;

  // Merge persisted forecasts with live activity for roles not yet persisted
  const forecastByRole: Record<string, ModelForecast | undefined> = {};
  forecasts.forEach((f) => (forecastByRole[f.role] = f));

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-stone-800">Prediction Engine</h1>
          <p className="text-sm text-stone-400 mt-0.5">5-role LLM ensemble, blended with XGBoost post-cold-start.</p>
        </div>
        {calibration && (
          <span
            className={clsx(
              "text-xs font-semibold px-3 py-1.5 rounded-full border",
              calibration.xgboost_active
                ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                : "bg-stone-100 text-stone-500 border-stone-200"
            )}
          >
            {calibration.xgboost_active
              ? "XGBoost: active"
              : `XGBoost: cold-start (${calibration.settled_trade_count}/${calibration.xgboost_min_samples})`}
          </span>
        )}
      </div>

      {/* Signal selector */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-4">
        {isLoading ? (
          <p className="text-stone-400 text-sm">Loading signals…</p>
        ) : signals.length === 0 ? (
          <p className="text-stone-400 text-sm">No prediction signals yet.</p>
        ) : (
          <div className="flex gap-2 overflow-x-auto">
            {signals.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedSignalId(s.id)}
                className={clsx(
                  "px-3 py-2 rounded-lg text-xs text-left shrink-0 border transition-colors",
                  selectedSignalId === s.id
                    ? "border-indigo-300 bg-indigo-50"
                    : "border-stone-200 hover:border-stone-300"
                )}
              >
                <p className="font-medium text-stone-700 truncate max-w-[180px]">
                  {s.market?.question ?? s.market_id}
                </p>
                <p className="text-stone-400 mt-0.5">{s.action} · edge {(s.edge * 100).toFixed(1)}%</p>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Role cards */}
      <div className="grid grid-cols-5 gap-3">
        {ROLE_ORDER.map((role) => {
          const persisted = forecastByRole[role];
          const live = predictionActivity[role];
          const status: ForecastStatus = live?.status ?? persisted?.status ?? "thinking";
          const probability = live?.probability ?? persisted?.probability;
          const reasoning = live?.reasoning ?? persisted?.reasoning;
          const provider = live?.provider ?? persisted?.provider;
          const model = live?.model ?? persisted?.model;

          return (
            <div key={role} className="bg-white rounded-xl border border-stone-100 shadow-sm p-4 flex flex-col">
              <p className="text-xs font-semibold text-stone-700 mb-0.5">{ROLE_LABELS[role]}</p>
              <p className="text-[10px] text-stone-400 mb-2 truncate">
                {provider ?? "—"} / {model ?? "—"}
              </p>
              <span className={clsx("text-[10px] font-semibold px-2 py-0.5 rounded-full border self-start mb-2", STATUS_STYLE[status])}>
                {STATUS_LABEL[status]}
              </span>
              {status === "ok" && probability != null && (
                <p className="text-lg font-bold text-stone-900 mb-1">{(probability * 100).toFixed(0)}%</p>
              )}
              {reasoning && (
                <p className="text-[11px] text-stone-500 leading-snug line-clamp-6">{reasoning}</p>
              )}
            </div>
          );
        })}
      </div>

      {/* Aggregate panel */}
      {selectedSignal && (
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-stone-700 mb-4">Aggregate Signal</h2>
          <div className="grid grid-cols-4 gap-4">
            <Stat label="Ensemble Probability" value={`${(selectedSignal.ensemble_probability * 100).toFixed(1)}%`} tooltip="Weighted average of all 'ok' role probabilities, before any XGBoost blending." />
            <Stat label="Final Probability" value={`${(selectedSignal.final_probability * 100).toFixed(1)}%`} tooltip="Final probability after XGBoost blending (if active) — used for the edge/EV calculation." />
            <Stat label="Edge" value={`${selectedSignal.edge >= 0 ? "+" : ""}${(selectedSignal.edge * 100).toFixed(1)}%`} tooltip="Final probability minus current market price. Positive edge favors YES, negative favors NO." />
            <Stat label="Expected Value" value={selectedSignal.expected_value.toFixed(3)} tooltip="Expected value per $1 staked, given the final probability and market price." />
            <Stat label="Z-Score" value={selectedSignal.z_score.toFixed(2)} tooltip="Standard deviations the edge is from 0, given ensemble disagreement — a confidence measure." />
            <Stat label="Action" value={selectedSignal.action} tooltip="BUY_YES / BUY_NO if edge clears the threshold, WATCH if borderline, SKIP otherwise." />
            <Stat label="Market Price" value={`$${selectedSignal.market_price.toFixed(3)}`} tooltip="Current Polymarket YES price at signal time." />
            <Stat label="XGBoost Used" value={selectedSignal.used_xgboost ? "Yes" : "No"} tooltip="Whether the XGBoost blend model was active for this signal (requires the cold-start sample threshold to be met)." />
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tooltip }: { label: string; value: string; tooltip: string }) {
  return (
    <div>
      <p className="text-xs text-stone-400 mb-0.5 flex items-center">
        {label}
        <InfoTooltip text={tooltip} />
      </p>
      <p className="text-base font-bold text-stone-800">{value}</p>
    </div>
  );
}

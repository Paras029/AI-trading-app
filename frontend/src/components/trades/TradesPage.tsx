import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import type { Trade, TradeDetail, Mode } from "../../types";
import clsx from "clsx";
import { ConfirmPhraseInput } from "../ui/ConfirmPhraseInput";

const MODE_OPTIONS: { id: Mode | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "paper", label: "Paper" },
  { id: "live", label: "Live" },
];

const CLOSE_ALL_PHRASE = "CLOSE ALL TRADES";

export function TradesPage() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode | "all">("all");
  const [openOnly, setOpenOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: trades = [], isLoading } = useQuery<Trade[]>({
    queryKey: ["trades", mode, openOnly],
    queryFn: () =>
      axios
        .get("/api/trades", {
          params: { mode: mode === "all" ? undefined : mode, open_only: openOnly || undefined },
        })
        .then((r) => r.data),
    refetchInterval: 10000,
  });

  const { data: detail } = useQuery<TradeDetail>({
    queryKey: ["trade-detail", selectedId],
    queryFn: () => axios.get(`/api/trades/${selectedId}`).then((r) => r.data),
    enabled: !!selectedId,
  });

  const closeMutation = useMutation({
    mutationFn: (tradeId: string) => axios.post(`/api/trades/${tradeId}/close`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trades"] });
      qc.invalidateQueries({ queryKey: ["trade-detail"] });
    },
  });

  const closeAllMutation = useMutation({
    mutationFn: () =>
      axios
        .post("/api/trades/close-all", null, { params: { mode: mode === "all" ? "paper" : mode } })
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trades"] });
      qc.invalidateQueries({ queryKey: ["trade-detail"] });
    },
  });

  const closeAllMode = mode === "all" ? "paper" : mode;
  const openCount = trades.filter((t) => t.status === "open" && t.mode === closeAllMode).length;

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-stone-800">Trades</h1>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {MODE_OPTIONS.map((m) => (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                className={clsx(
                  "px-2.5 py-1 rounded text-xs font-medium transition-colors",
                  mode === m.id ? "bg-active-nav text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setOpenOnly((v) => !v)}
            className={clsx(
              "px-2.5 py-1 rounded text-xs font-medium border transition-colors",
              openOnly ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "border-stone-200 text-stone-500 hover:border-stone-300"
            )}
          >
            Open Only
          </button>
        </div>
      </div>

      <div className="border-2 border-red-300 rounded-xl p-4 bg-red-50/40 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold text-red-700">Close All Open Trades ({closeAllMode})</p>
          <span className="text-xs text-red-700/70">{openCount} open</span>
        </div>
        <p className="text-xs text-red-700/80 leading-relaxed">
          Closes every open trade in <span className="font-semibold">{closeAllMode}</span> mode at the
          current market price, independent of whether the bot is running or stopped.
        </p>
        <ConfirmPhraseInput
          phrase={CLOSE_ALL_PHRASE}
          onConfirm={() => closeAllMutation.mutate()}
          disabled={openCount === 0}
          pending={closeAllMutation.isPending}
          buttonLabel={`Close All ${closeAllMode} Trades`}
        />
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 bg-white rounded-2xl border border-stone-100 shadow-sm divide-y divide-stone-50">
          {isLoading && <p className="p-8 text-center text-stone-400">Loading…</p>}
          {!isLoading && trades.length === 0 && (
            <p className="p-8 text-center text-stone-400">No trades yet.</p>
          )}
          {trades.map((t) => (
            <TradeRow
              key={t.id}
              trade={t}
              selected={t.id === selectedId}
              onSelect={() => setSelectedId(t.id)}
              onClose={() => closeMutation.mutate(t.id)}
              closing={closeMutation.isPending && closeMutation.variables === t.id}
            />
          ))}
        </div>

        {/* Drill-down panel */}
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
          {!detail ? (
            <p className="text-stone-400 text-sm">Select a trade to see its originating signal, forecasts, and gate checks.</p>
          ) : (
            <div className="space-y-4">
              <div>
                <p className="text-xs text-stone-400">Market</p>
                <p className="text-sm font-medium text-stone-800">{detail.market?.question ?? detail.market_id}</p>
              </div>
              {detail.signal && (
                <div>
                  <p className="text-xs text-stone-400 mb-1">Signal</p>
                  <p className="text-xs text-stone-600">
                    final prob {(detail.signal.final_probability * 100).toFixed(1)}% · edge{" "}
                    {(detail.signal.edge * 100).toFixed(1)}% · {detail.signal.action}
                  </p>
                </div>
              )}
              {detail.forecasts && detail.forecasts.length > 0 && (
                <div>
                  <p className="text-xs text-stone-400 mb-1">Forecasts</p>
                  <div className="space-y-1">
                    {detail.forecasts.map((f) => (
                      <div key={f.id} className="text-xs text-stone-600 flex justify-between">
                        <span>{f.role}</span>
                        <span>{f.status === "ok" ? `${((f.probability ?? 0) * 100).toFixed(0)}%` : f.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {detail.gate_checks && detail.gate_checks.length > 0 && (
                <div>
                  <p className="text-xs text-stone-400 mb-1">Gate Checks</p>
                  <div className="space-y-1">
                    {detail.gate_checks.map((g) => (
                      <div key={g.id} className="text-xs flex justify-between">
                        <span className="text-stone-600">{g.gate_name}</span>
                        <span className={g.passed ? "text-emerald-600" : "text-red-500"}>
                          {g.passed === null ? "skipped" : g.passed ? "pass" : "fail"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TradeRow({
  trade: t,
  selected,
  onSelect,
  onClose,
  closing,
}: {
  trade: Trade;
  selected: boolean;
  onSelect: () => void;
  onClose: () => void;
  closing: boolean;
}) {
  const isOpen = t.status === "open";
  const pnlColor = (t.pnl ?? 0) >= 0 ? "text-positive" : "text-negative";

  return (
    <div
      className={clsx("flex items-center gap-3 px-4 py-3 w-full text-left hover:bg-stone-50 transition-colors", selected && "bg-indigo-50")}
    >
      <button onClick={onSelect} className="flex items-center gap-3 flex-1 min-w-0 text-left">
        <span
          className={clsx(
            "text-[10px] font-bold px-1.5 py-0.5 rounded uppercase",
            isOpen ? "bg-blue-100 text-blue-600" : "bg-stone-100 text-stone-500"
          )}
        >
          {t.status.replace("settled_", "")}
        </span>
        <span
          className={clsx(
            "text-xs font-bold px-1.5 py-0.5 rounded",
            t.side === "YES" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
          )}
        >
          {t.side}
        </span>
        <span className="font-medium text-stone-800 text-sm truncate flex-1">
          {t.market?.question ?? t.market_id}
        </span>
        <span className="text-xs text-stone-400 bg-stone-50 px-2 py-0.5 rounded-full">{t.mode}</span>
        <span className="text-xs text-stone-400">${t.stake_usdc.toFixed(2)}</span>
        {t.pnl != null && (
          <span className={clsx("text-sm font-semibold", pnlColor)}>
            {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
          </span>
        )}
      </button>
      {isOpen && (
        <button
          onClick={() => {
            if (window.confirm(`Close this ${t.mode} trade now at the current market price?`)) {
              onClose();
            }
          }}
          disabled={closing}
          className="shrink-0 px-2.5 py-1 text-xs font-medium rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {closing ? "Closing…" : "Close"}
        </button>
      )}
    </div>
  );
}

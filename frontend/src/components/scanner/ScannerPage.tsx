import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { ScannerFilters, MarketScan } from "../../types";
import { InfoTooltip } from "../ui/InfoTooltip";
import clsx from "clsx";

const CATEGORY_OPTIONS = ["politics", "sports", "crypto", "economy", "pop-culture", "science"];

export function ScannerPage() {
  const qc = useQueryClient();
  const { scannerLog } = useStore();
  const [localFilters, setLocalFilters] = useState<ScannerFilters | null>(null);

  const { data: filters } = useQuery<ScannerFilters>({
    queryKey: ["scanner-filters"],
    queryFn: () => axios.get("/api/scanner/filters").then((r) => r.data),
  });

  const { data: scans = [], isLoading } = useQuery<MarketScan[]>({
    queryKey: ["scanner-scans"],
    queryFn: () => axios.get("/api/scanner/scans").then((r) => r.data),
    refetchInterval: 15000,
  });

  useEffect(() => {
    if (filters && !localFilters) setLocalFilters(filters);
  }, [filters, localFilters]);

  const saveMutation = useMutation({
    mutationFn: (patch: Partial<ScannerFilters>) =>
      axios.put("/api/scanner/filters", patch).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scanner-filters"] }),
  });

  const scanNowMutation = useMutation({
    mutationFn: () => axios.post("/api/scanner/scan-now").then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scanner-scans"] }),
  });

  if (!localFilters) return <div className="text-stone-400">Loading...</div>;

  function toggleCategory(cat: string) {
    if (!localFilters) return;
    const has = localFilters.categories.includes(cat);
    const next = has
      ? localFilters.categories.filter((c) => c !== cat)
      : [...localFilters.categories, cat];
    setLocalFilters({ ...localFilters, categories: next });
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-stone-800">Scanner</h1>
          <p className="text-sm text-stone-400 mt-0.5">
            Cheap pre-filter over live Polymarket markets before any AI spend.
          </p>
        </div>
        <button
          onClick={() => scanNowMutation.mutate()}
          disabled={scanNowMutation.isPending}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {scanNowMutation.isPending ? "Scanning…" : "Scan Now"}
        </button>
      </div>

      {/* Filter bar */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5 space-y-4">
        <h2 className="text-sm font-semibold text-stone-700">Filters</h2>
        <div>
          <p className="text-xs text-stone-400 mb-2">Categories</p>
          <div className="flex flex-wrap gap-2">
            {CATEGORY_OPTIONS.map((cat) => (
              <button
                key={cat}
                onClick={() => toggleCategory(cat)}
                className={clsx(
                  "px-3 py-1 rounded-full text-xs font-medium border transition-colors capitalize",
                  localFilters.categories.includes(cat)
                    ? "bg-indigo-600 text-white border-indigo-600"
                    : "bg-white text-stone-600 border-stone-200 hover:border-stone-300"
                )}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <NumberField
            label="Min Volume ($)"
            value={localFilters.min_volume}
            onChange={(v) => setLocalFilters({ ...localFilters, min_volume: v })}
          />
          <NumberField
            label="Max Expiry (days)"
            value={localFilters.max_expiry_days}
            onChange={(v) => setLocalFilters({ ...localFilters, max_expiry_days: v })}
          />
          <NumberField
            label="Min Edge (%)"
            value={localFilters.min_edge_pct}
            step={0.01}
            onChange={(v) => setLocalFilters({ ...localFilters, min_edge_pct: v })}
          />
        </div>
        <div className="flex justify-end">
          <button
            onClick={() => saveMutation.mutate(localFilters)}
            disabled={saveMutation.isPending}
            className="px-3 py-1.5 text-xs font-medium rounded border border-indigo-300 text-indigo-700 hover:bg-indigo-50 disabled:opacity-40 transition-colors"
          >
            {saveMutation.isPending ? "Saving…" : "Save Filters"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Results table */}
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm">
          <h2 className="text-sm font-semibold text-stone-700 px-5 pt-5 pb-3">Recent Scans</h2>
          <div className="divide-y divide-stone-50 max-h-[480px] overflow-auto">
            {isLoading && <p className="p-5 text-stone-400 text-sm">Loading…</p>}
            {!isLoading && scans.length === 0 && (
              <p className="p-5 text-stone-400 text-sm">No scans yet. Click "Scan Now".</p>
            )}
            {scans.map((s) => <ScanRow key={s.id} scan={s} />)}
          </div>
        </div>

        {/* Live activity log */}
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm">
          <h2 className="text-sm font-semibold text-stone-700 px-5 pt-5 pb-3 flex items-center">
            Activity Log
            <InfoTooltip text="Live stream of scanner activity as markets are evaluated, newest first." />
          </h2>
          <div className="divide-y divide-stone-50 max-h-[480px] overflow-auto font-mono text-xs">
            {scannerLog.length === 0 && (
              <p className="p-5 text-stone-400 text-sm font-sans">Waiting for scanner activity…</p>
            )}
            {scannerLog.map((e, i) => (
              <div key={i} className="px-4 py-2 text-stone-600 leading-relaxed">
                <span className="text-stone-300 mr-2">{new Date(e.ts).toLocaleTimeString()}</span>
                {e.passed === true && <span className="text-emerald-600 mr-1">[PASS]</span>}
                {e.passed === false && <span className="text-red-500 mr-1">[REJECT]</span>}
                {e.message}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
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
        className="w-full border border-stone-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200"
      />
    </label>
  );
}

function ScanRow({ scan: s }: { scan: MarketScan }) {
  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span
          className={clsx(
            "text-[10px] font-bold px-1.5 py-0.5 rounded uppercase shrink-0",
            s.passed ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"
          )}
        >
          {s.passed ? "pass" : "reject"}
        </span>
        <span className="text-sm text-stone-800 truncate flex-1">
          {s.market?.question ?? s.market_id}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs text-stone-400">
        <span>${s.price_at_scan?.toFixed(3)}</span>
        <span>vol ${s.volume_at_scan?.toLocaleString()}</span>
        {!s.passed && s.reject_reason && (
          <span className="text-red-400 truncate">{s.reject_reason}</span>
        )}
      </div>
    </div>
  );
}

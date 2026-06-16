import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import type { WorldContext } from "../../types";
import clsx from "clsx";

function FngGauge({ value, label, title }: { value: number; label: string; title: string }) {
  const color = value < 25 ? "text-red-600" : value < 45 ? "text-orange-500" : value < 55 ? "text-yellow-500" : value < 75 ? "text-green-500" : "text-green-700";
  const barColor = value < 25 ? "bg-red-500" : value < 45 ? "bg-orange-400" : value < 55 ? "bg-yellow-400" : value < 75 ? "bg-green-400" : "bg-green-600";
  return (
    <div className="bg-white rounded-xl border border-stone-100 p-4">
      <p className="text-xs text-stone-400 mb-1">{title}</p>
      <p className={clsx("font-bold text-lg", color)}>{label}</p>
      <div className="mt-2 h-2 bg-stone-100 rounded-full overflow-hidden">
        <div className={clsx("h-full rounded-full", barColor)} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export function WorldPage() {
  const { data, isLoading } = useQuery<WorldContext>({
    queryKey: ["world"],
    queryFn: () => axios.get("/api/world").then((r) => r.data),
    refetchInterval: 60000,
  });

  if (isLoading || !data) return <div className="text-stone-400">Loading world data...</div>;

  const cryptoHeadlines = data.headlines?.crypto ?? [];
  const usHeadlines = data.headlines?.us ?? [];
  const indiaHeadlines = data.headlines?.india ?? [];

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-xl font-semibold text-stone-800">World Context</h1>

      {/* Fear & Greed */}
      <div className="grid grid-cols-2 gap-4">
        <FngGauge value={data.crypto_fng?.value ?? 50} label={data.crypto_fng?.label ?? "Neutral"} title="Crypto Fear & Greed" />
        <FngGauge value={data.stock_fng?.value ?? 50} label={data.stock_fng?.label ?? "Neutral"} title="Stock Fear & Greed (CNN)" />
      </div>

      {/* Macro & Flow */}
      <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
        <h2 className="font-semibold text-stone-800 mb-3">Macro & Flow</h2>
        <div className="grid grid-cols-2 gap-3 mb-3 text-sm">
          <div>
            <p className="text-xs text-stone-400">Regime</p>
            <p className={clsx("font-semibold", data.regime === "Risk Off" ? "text-red-600" : data.regime === "Risk On" ? "text-green-600" : "text-stone-700")}>
              {data.regime}
            </p>
          </div>
          <div>
            <p className="text-xs text-stone-400">Funding Rate (BTC)</p>
            <p className="font-semibold text-stone-700">{((data.funding_rate ?? 0) * 100).toFixed(4)}%</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs text-stone-600">
          {Object.entries(data.macro ?? {}).map(([k, v]) => (
            <div key={k} className="bg-stone-50 rounded-lg px-2 py-1.5">
              <p className="text-stone-400 text-[10px]">{k}</p>
              <p className="font-semibold">{typeof v === "number" ? v.toLocaleString() : v}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Headlines by market */}
      {[
        { title: "Crypto Headlines", items: cryptoHeadlines },
        { title: "US Headlines", items: usHeadlines },
        { title: "India Headlines", items: indiaHeadlines },
      ].map(({ title, items }) => items.length > 0 && (
        <div key={title} className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
          <h2 className="font-semibold text-stone-800 mb-3">{title}</h2>
          <ul className="space-y-2">
            {items.map((h, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-stone-600">
                <span className="text-stone-300 mt-0.5">·</span>
                {h}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

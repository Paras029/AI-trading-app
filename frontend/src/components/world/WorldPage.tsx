import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { formatDistanceToNow } from "date-fns";
import type { WorldContext, Headline } from "../../types";
import { InfoTooltip } from "../ui/InfoTooltip";
import clsx from "clsx";

function FngGauge({ value, label, title, tooltip }: { value: number; label: string; title: string; tooltip: string }) {
  const color =
    value < 25 ? "text-red-600" :
    value < 45 ? "text-orange-500" :
    value < 55 ? "text-yellow-600" :
    value < 75 ? "text-emerald-600" : "text-emerald-700";
  const barColor =
    value < 25 ? "bg-red-500" :
    value < 45 ? "bg-orange-400" :
    value < 55 ? "bg-yellow-400" :
    value < 75 ? "bg-emerald-400" : "bg-emerald-600";

  return (
    <div className="bg-white rounded-xl border border-stone-100 shadow-sm p-4">
      <p className="text-xs text-stone-400 mb-1 flex items-center">
        {title}
        <InfoTooltip text={tooltip} />
      </p>
      <p className={clsx("font-bold text-xl mt-0.5", color)}>{label}</p>
      <p className="text-sm text-stone-500">{value} / 100</p>
      <div className="mt-2 h-2 bg-stone-100 rounded-full overflow-hidden">
        <div className={clsx("h-full rounded-full transition-all", barColor)} style={{ width: `${value}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-stone-300 mt-1">
        <span>Extreme Fear</span>
        <span>Neutral</span>
        <span>Extreme Greed</span>
      </div>
    </div>
  );
}

function HeadlineList({ title, items }: { title: string; items: Headline[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="bg-white rounded-xl border border-stone-100 shadow-sm p-4">
      <h2 className="text-sm font-semibold text-stone-700 mb-2">{title}</h2>
      <div className="divide-y divide-stone-50">
        {items.map((h, i) => {
          const hostname = (() => {
            try { return new URL(h.url).hostname.replace("www.", ""); }
            catch { return ""; }
          })();
          return h.url ? (
            <a
              key={i}
              href={h.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block py-2 first:pt-0 last:pb-0 hover:bg-stone-50 -mx-1 px-1 rounded transition-colors group"
            >
              <p className="text-sm text-stone-800 leading-snug group-hover:text-indigo-700">{h.title}</p>
              {hostname && <p className="text-[11px] text-stone-400 mt-0.5">{hostname} ↗</p>}
            </a>
          ) : (
            <div key={i} className="py-2 first:pt-0 last:pb-0">
              <p className="text-sm text-stone-700 leading-snug">{h.title}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const MACRO_LABELS: Record<string, { label: string; tooltip: string }> = {
  VIX:     { label: "VIX", tooltip: "Volatility Index. >30 = high fear, market expects large swings. <15 = calm market." },
  DXY:     { label: "DXY (USD)", tooltip: "US Dollar strength index. Higher DXY = stronger dollar, often pressures crypto and emerging markets." },
  US10Y:   { label: "US 10Y Yield", tooltip: "US 10-year Treasury yield. Rising yields = tighter money = pressure on growth stocks and crypto." },
  GOLD:    { label: "Gold", tooltip: "Price of gold per troy ounce. Rises in uncertainty and inflation." },
  OIL:     { label: "Oil (WTI)", tooltip: "Crude oil price. Affects inflation and energy sector stocks." },
  SP500:   { label: "S&P 500", tooltip: "Index of the 500 largest US companies. Main benchmark for US stock market health." },
  NIFTY50: { label: "Nifty 50", tooltip: "Index of the 50 largest companies on the NSE (India's main stock exchange)." },
  SENSEX:  { label: "Sensex", tooltip: "Index of 30 large companies on the BSE (Bombay Stock Exchange)." },
  BTCUSD:  { label: "BTC/USD", tooltip: "Bitcoin price in US dollars via Yahoo Finance." },
};

export function WorldPage() {
  const { data, isLoading } = useQuery<WorldContext>({
    queryKey: ["world"],
    queryFn: () => axios.get("/api/world").then((r) => r.data),
    refetchInterval: 60000,
  });

  if (isLoading || !data) {
    return <div className="text-stone-400 p-6">Loading world data…</div>;
  }

  const updatedAgo = data.updated_at
    ? formatDistanceToNow(new Date(data.updated_at), { addSuffix: true })
    : null;

  const regimeColor =
    data.regime === "Risk Off" ? "text-red-600 bg-red-50 border-red-200" :
    data.regime === "Risk On" ? "text-emerald-700 bg-emerald-50 border-emerald-200" :
    "text-stone-700 bg-stone-50 border-stone-200";

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-stone-800">World Context</h1>
        {updatedAgo && (
          <span className="text-xs text-stone-400">Updated {updatedAgo}</span>
        )}
      </div>

      {/* Regime + Funding */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-stone-100 shadow-sm p-4">
          <p className="text-xs text-stone-400 mb-1 flex items-center">
            Market Regime
            <InfoTooltip text="Overall market sentiment direction. Risk On = investors buying riskier assets. Risk Off = moving to safety (cash, bonds, gold)." />
          </p>
          <span className={clsx("inline-block text-sm font-semibold px-2.5 py-1 rounded-full border mt-1", regimeColor)}>
            {data.regime}
          </span>
        </div>
        <div className="bg-white rounded-xl border border-stone-100 shadow-sm p-4">
          <p className="text-xs text-stone-400 mb-1 flex items-center">
            BTC Funding Rate
            <InfoTooltip text="Fee paid between crypto futures long/short holders every 8 hours. Positive = longs pay shorts (market leans bullish). Extreme values (>0.1%) signal crowded trades and potential reversal." />
          </p>
          <p className={clsx("text-xl font-bold mt-0.5", (data.funding_rate ?? 0) > 0 ? "text-emerald-600" : "text-red-500")}>
            {((data.funding_rate ?? 0) * 100).toFixed(4)}%
          </p>
        </div>
      </div>

      {/* Fear & Greed */}
      <div className="grid grid-cols-2 gap-4">
        <FngGauge
          value={data.crypto_fng?.value ?? 50}
          label={data.crypto_fng?.label ?? "Neutral"}
          title="Crypto Fear & Greed"
          tooltip="Measures how greedy (euphoric) or fearful (panicked) crypto traders are right now. Extreme Fear (<25) often marks market bottoms — historically a buying signal. Extreme Greed (>75) often precedes corrections."
        />
        <FngGauge
          value={data.stock_fng?.value ?? 50}
          label={data.stock_fng?.label ?? "Neutral"}
          title="Stock Fear & Greed"
          tooltip="CNN's Fear & Greed index for US stocks. Combines 7 indicators: momentum, breadth, put/call ratio, junk bond demand, safe haven demand, volatility, and market volume. A composite view of whether investors are fearful or greedy."
        />
      </div>

      {/* Macro indicators */}
      {Object.keys(data.macro ?? {}).length > 0 && (
        <div className="bg-white rounded-xl border border-stone-100 shadow-sm p-4">
          <h2 className="text-sm font-semibold text-stone-700 mb-3">Macro Indicators</h2>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(data.macro).map(([k, v]) => {
              const meta = MACRO_LABELS[k];
              return (
                <div key={k} className="bg-stone-50 rounded-lg px-3 py-2">
                  <p className="text-[10px] text-stone-400 flex items-center">
                    {meta?.label ?? k}
                    {meta?.tooltip && <InfoTooltip text={meta.tooltip} />}
                  </p>
                  <p className="text-sm font-semibold text-stone-800 mt-0.5">
                    {typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Upcoming events */}
      {data.upcoming_events && data.upcoming_events.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-amber-800 mb-2">⚠ Upcoming High-Impact Events</h2>
          <div className="space-y-1.5">
            {data.upcoming_events.map((ev, i) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="text-amber-900">{ev.title} <span className="text-amber-600 text-xs">({ev.country})</span></span>
                <span className="text-amber-700 font-medium">in {ev.hours_until}h</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Headlines */}
      <HeadlineList title="Crypto Headlines" items={data.headlines?.crypto ?? []} />
      <HeadlineList title="US Market Headlines" items={data.headlines?.us ?? []} />
      <HeadlineList title="India Market Headlines" items={data.headlines?.india ?? []} />
    </div>
  );
}

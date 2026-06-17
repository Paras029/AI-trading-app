import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useStore } from "../../store";
import type { ResearchBrief } from "../../types";
import { InfoTooltip } from "../ui/InfoTooltip";
import clsx from "clsx";

function SentimentGauge({ bullish, bearish, neutral }: { bullish: number; bearish: number; neutral: number }) {
  const bullDeg = bullish * 3.6;
  const bearDeg = bearish * 3.6;
  const gradient = `conic-gradient(#059669 0deg ${bullDeg}deg, #dc2626 ${bullDeg}deg ${bullDeg + bearDeg}deg, #d6d3d1 ${bullDeg + bearDeg}deg 360deg)`;

  return (
    <div className="flex items-center gap-4">
      <div
        className="w-24 h-24 rounded-full flex items-center justify-center shrink-0"
        style={{ background: gradient }}
      >
        <div className="w-16 h-16 rounded-full bg-white flex flex-col items-center justify-center">
          <span className="text-sm font-bold text-stone-800">{bullish.toFixed(0)}%</span>
          <span className="text-[9px] text-stone-400">bullish</span>
        </div>
      </div>
      <div className="space-y-1 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-600" /> Bullish {bullish.toFixed(1)}%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-red-600" /> Bearish {bearish.toFixed(1)}%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-stone-300" /> Neutral {neutral.toFixed(1)}%
        </div>
      </div>
    </div>
  );
}

export function ResearchPage() {
  const { researchLog } = useStore();
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);

  const { data: briefs = [], isLoading } = useQuery<ResearchBrief[]>({
    queryKey: ["research-briefs"],
    queryFn: () => axios.get("/api/research/briefs").then((r) => r.data),
    refetchInterval: 15000,
  });

  useEffect(() => {
    if (!selectedMarketId && briefs.length > 0) {
      setSelectedMarketId(briefs[0].market_id);
    }
  }, [briefs, selectedMarketId]);

  const { data: brief } = useQuery<ResearchBrief>({
    queryKey: ["research-brief", selectedMarketId],
    queryFn: () =>
      axios.get(`/api/research/briefs/${selectedMarketId}`).then((r) => r.data),
    enabled: !!selectedMarketId,
  });

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-stone-800">Research</h1>
        <p className="text-sm text-stone-400 mt-0.5 flex items-center">
          Sentiment-weighted narrative vs. market-implied probability
          <InfoTooltip text="Twitter/X sentiment is approximated via Reddit + News RSS in this version." />
        </p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Market list */}
        <div className="bg-white rounded-2xl border border-stone-100 shadow-sm divide-y divide-stone-50 max-h-[600px] overflow-auto">
          {isLoading && <p className="p-5 text-stone-400 text-sm">Loading…</p>}
          {!isLoading && briefs.length === 0 && (
            <p className="p-5 text-stone-400 text-sm">No research briefs yet.</p>
          )}
          {briefs.map((b) => (
            <button
              key={b.id}
              onClick={() => setSelectedMarketId(b.market_id)}
              className={clsx(
                "w-full text-left px-4 py-3 hover:bg-stone-50 transition-colors",
                selectedMarketId === b.market_id && "bg-indigo-50"
              )}
            >
              <p className="text-sm text-stone-800 truncate">{b.market?.question ?? b.market_id}</p>
              <p className="text-xs text-stone-400 mt-0.5">
                gap {b.gap_pct >= 0 ? "+" : ""}{b.gap_pct.toFixed(1)}%
              </p>
            </button>
          ))}
        </div>

        {/* Detail */}
        <div className="col-span-2 space-y-4">
          {!brief ? (
            <div className="bg-white rounded-2xl border border-stone-100 p-8 text-center text-stone-400">
              Select a market to view its research brief.
            </div>
          ) : (
            <>
              <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
                <p className="text-sm font-medium text-stone-800 mb-3">
                  {brief.market?.question ?? brief.market_id}
                </p>
                <div className="flex items-center justify-between">
                  <SentimentGauge
                    bullish={brief.bullish_pct}
                    bearish={brief.bearish_pct}
                    neutral={brief.neutral_pct}
                  />
                  <div className="space-y-2 text-right">
                    <div>
                      <p className="text-xs text-stone-400 flex items-center justify-end">
                        Source Agreement
                        <InfoTooltip text="How much the sources (Reddit + News) agree on direction. High agreement = more confidence in the narrative signal." />
                      </p>
                      <p className="text-lg font-bold text-stone-800">{brief.source_agreement_pct.toFixed(0)}%</p>
                    </div>
                    <div>
                      <p className="text-xs text-stone-400 flex items-center justify-end">
                        Narrative vs Market Gap
                        <InfoTooltip text="Difference between the sentiment-derived narrative probability and the current market-implied probability. A large gap suggests the market may be mispricing the outcome." />
                      </p>
                      <p className={clsx("text-lg font-bold", brief.gap_pct >= 0 ? "text-positive" : "text-negative")}>
                        {brief.gap_pct >= 0 ? "+" : ""}{brief.gap_pct.toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>
                <div className="flex gap-4 mt-3 text-xs text-stone-400">
                  <span>Narrative prob: {(brief.narrative_probability * 100).toFixed(1)}%</span>
                  <span>Market prob: {(brief.market_implied_probability * 100).toFixed(1)}%</span>
                </div>
                {brief.brief_text && (
                  <p className="text-sm text-stone-600 leading-relaxed mt-3 border-t border-stone-50 pt-3">
                    {brief.brief_text}
                  </p>
                )}
              </div>

              {/* Sources */}
              <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-5">
                <h3 className="text-sm font-semibold text-stone-700 mb-3">Sources</h3>
                {brief.sources?.length === 0 || !brief.sources ? (
                  <p className="text-stone-400 text-sm">No sources recorded.</p>
                ) : (
                  <div className="space-y-2">
                    {brief.sources.map((src, i) => (
                      <div key={i} className="flex items-center justify-between gap-2 text-sm border-b border-stone-50 last:border-0 pb-2 last:pb-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-[10px] uppercase font-bold text-stone-400 bg-stone-100 px-1.5 py-0.5 rounded shrink-0">
                            {src.source}
                          </span>
                          {src.url ? (
                            <a href={src.url} target="_blank" rel="noopener noreferrer" className="truncate text-stone-700 hover:text-indigo-700">
                              {src.title}
                            </a>
                          ) : (
                            <span className="truncate text-stone-700">{src.title}</span>
                          )}
                        </div>
                        <span
                          className={clsx(
                            "text-[10px] font-bold px-1.5 py-0.5 rounded uppercase shrink-0",
                            src.sentiment === "bullish" && "bg-emerald-100 text-emerald-700",
                            src.sentiment === "bearish" && "bg-red-100 text-red-600",
                            src.sentiment === "neutral" && "bg-stone-100 text-stone-500"
                          )}
                        >
                          {src.sentiment}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* Live reasoning log */}
          <div className="bg-white rounded-2xl border border-stone-100 shadow-sm">
            <h3 className="text-sm font-semibold text-stone-700 px-5 pt-5 pb-3">Live Reasoning Log</h3>
            <div className="divide-y divide-stone-50 max-h-64 overflow-auto font-mono text-xs">
              {researchLog.length === 0 && (
                <p className="p-5 text-stone-400 text-sm font-sans">Waiting for research activity…</p>
              )}
              {researchLog.map((e, i) => (
                <div key={i} className="px-4 py-2 text-stone-600 leading-relaxed">
                  <span className="text-stone-300 mr-2">{new Date(e.ts).toLocaleTimeString()}</span>
                  <span className="text-indigo-500 mr-1">[{e.step}]</span>
                  {e.message}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

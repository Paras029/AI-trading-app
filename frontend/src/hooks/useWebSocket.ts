import { useEffect, useRef } from "react";
import { useStore } from "../store";
import type {
  WsMessage,
  ScannerActivityEvent,
  ResearchActivityEvent,
  RiskActivityEvent,
  RiskDecision,
  PredictionActivityEvent,
  PostMortem,
  PipelineStatusEvent,
} from "../types";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";
const RECONNECT_DELAY = 3000;

export function useWebSocket(market: string = "all") {
  const ws = useRef<WebSocket | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const {
    addScannerLog,
    addResearchLog,
    addRiskLog,
    setPredictionActivity,
    setPipelineStatus,
    addTrade,
    setNotification,
  } = useStore();

  function connect() {
    const socket = new WebSocket(`${WS_URL}?market=${market}`);
    ws.current = socket;

    socket.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        const d = msg.data as Record<string, unknown>;

        switch (msg.type) {
          case "scanner_activity":
            addScannerLog(d as unknown as ScannerActivityEvent);
            break;
          case "research_activity":
            addResearchLog(d as unknown as ResearchActivityEvent);
            break;
          case "prediction_activity": {
            const ev = d as unknown as PredictionActivityEvent;
            setPredictionActivity(ev.role, ev);
            break;
          }
          case "risk_activity":
            addRiskLog(d as unknown as RiskActivityEvent);
            break;
          case "risk_decision": {
            const ev = d as unknown as RiskDecision;
            setNotification(
              `${ev.approved ? "Trade approved" : "Trade rejected"} — signal ${ev.signal_id}`
            );
            break;
          }
          case "postmortem_new": {
            const ev = d as unknown as PostMortem;
            setNotification(`Post-mortem: ${ev.outcome} — ${ev.lesson_title}`);
            break;
          }
          case "pipeline_status": {
            const ev = d as unknown as PipelineStatusEvent;
            setPipelineStatus(ev, ev.system_status);
            break;
          }
          case "trade_update":
            addTrade(d as never);
            break;
        }
      } catch {
        // ignore malformed frames
      }
    };

    socket.onclose = () => {
      timer.current = setTimeout(connect, RECONNECT_DELAY);
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  useEffect(() => {
    connect();
    return () => {
      ws.current?.close();
      if (timer.current) clearTimeout(timer.current);
    };
  }, [market]);
}

import { useEffect, useRef } from "react";
import { useStore } from "../store";
import type { WsMessage } from "../types";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";
const RECONNECT_DELAY = 3000;

export function useWebSocket(market: string = "all") {
  const ws = useRef<WebSocket | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { setEpisode, addSignal, setWorld, setPrice, addTrade, setNotification } = useStore();

  function connect() {
    const socket = new WebSocket(`${WS_URL}?market=${market}`);
    ws.current = socket;

    socket.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        const d = msg.data as Record<string, unknown>;

        switch (msg.type) {
          case "price_tick":
            setPrice(d.symbol as string, d.price as number);
            break;
          case "signal_new":
            addSignal(d as never);
            break;
          case "world_update":
            setWorld(d as never);
            break;
          case "trade_update":
            addTrade(d as never);
            break;
          case "episode_update":
            setNotification(`Episode ${d.outcome} — Gen ${d.generation} | Equity: $${(d.final_equity as number)?.toFixed(2)}`);
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

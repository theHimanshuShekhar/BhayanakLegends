import { useEffect, useRef, useState } from "react";
import { eventsUrl } from "./client";

export interface SseMessage {
  type: string;
  ts: string;
  data: unknown;
}

export function useEvents(onMessage?: (msg: SseMessage) => void) {
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    let source: EventSource | null = null;
    let closed = false;

    const connect = () => {
      if (closed) return;
      source = new EventSource(eventsUrl());
      source.onopen = () => setConnected(true);
      source.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as SseMessage;
          handlerRef.current?.(msg);
        } catch {
          // ignore malformed frames
        }
      };
      source.onerror = () => {
        setConnected(false);
        source?.close();
        setTimeout(connect, 2000);
      };
    };

    connect();
    return () => {
      closed = true;
      source?.close();
    };
  }, []);

  return connected;
}

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

    const connect = async () => {
      if (closed) return;
      try {
        source = new EventSource(await eventsUrl());
      } catch {
        if (closed) return;
        setConnected(false);
        setTimeout(() => void connect(), 2000);
        return;
      }
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
        setTimeout(() => void connect(), 2000);
      };
    };

    void connect();
    return () => {
      closed = true;
      source?.close();
    };
  }, []);

  return connected;
}

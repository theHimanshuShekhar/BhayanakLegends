import { invoke } from "@tauri-apps/api/core";
import { useEffect, useRef, useState } from "react";
import { useEvents } from "../api/sse";
import type { SseMessage } from "../api/sse";

type LivePhase = "idle" | "champ-select" | "in-game";
type CompanionModeRequest =
  | { mode: "idle" }
  | { mode: "champ-select" }
  | { mode: "in-game"; expanded: boolean };
function syncWindowMode(request: CompanionModeRequest) {
  // Web-only development has no Tauri command handler; live UI remains usable.
  void invoke("set_live_companion_mode", request).catch(() => undefined);
}

function modeFromSources(champSelectActive: boolean, inGameActive: boolean): LivePhase {
  if (inGameActive) return "in-game";
  if (champSelectActive) return "champ-select";
  return "idle";
}

function requestFor(phase: LivePhase, expanded = false): CompanionModeRequest {
  if (phase === "champ-select") return { mode: "champ-select" };
  if (phase === "in-game") return { mode: "in-game", expanded };
  return { mode: "idle" };
}

export function LiveCompanion() {
  const [phase, setPhase] = useState<LivePhase>("idle");
  const [expanded, setExpanded] = useState(false);
  const phaseRef = useRef<LivePhase>("idle");
  const expandedRef = useRef(false);
  const sourcesRef = useRef({ champSelect: false, inGame: false });

  const applyPhase = (nextPhase: LivePhase) => {
    const nextExpanded = nextPhase === "in-game" ? expandedRef.current : false;
    if (phaseRef.current === nextPhase && expandedRef.current === nextExpanded) return;
    phaseRef.current = nextPhase;
    expandedRef.current = nextExpanded;
    setPhase(nextPhase);
    setExpanded(nextExpanded);
    syncWindowMode(requestFor(nextPhase, nextExpanded));
  };

  useEvents((message: SseMessage) => {
    if (message.type === "champselect.state") {
      sourcesRef.current.champSelect = message.data.active;
    } else if (message.type === "live.state") {
      sourcesRef.current.inGame = message.data.active;
    } else if (message.type === "live.status") {
      sourcesRef.current.champSelect = message.data.champ_select.active;
      sourcesRef.current.inGame = message.data.ingame.active;
    } else {
      return;
    }
    applyPhase(modeFromSources(sourcesRef.current.champSelect, sourcesRef.current.inGame));
  });

  useEffect(() => {
    document.documentElement.dataset.liveCompanion = phase === "in-game" ? "widget" : "normal";
    return () => {
      delete document.documentElement.dataset.liveCompanion;
    };
  }, [phase]);

  const toggleExpanded = () => {
    if (phaseRef.current !== "in-game") return;
    const nextExpanded = !expandedRef.current;
    expandedRef.current = nextExpanded;
    setExpanded(nextExpanded);
    syncWindowMode(requestFor("in-game", nextExpanded));
  };

  return (
    <aside
      className="live-companion"
      data-testid="live-companion"
      data-phase={phase}
      aria-live="polite"
    >
      <span data-testid="live-companion-mode">
        {phase === "champ-select" ? "champ select" : phase}
      </span>
      {phase === "in-game" ? (
        <>
          <button
            type="button"
            onClick={toggleExpanded}
            aria-label={`${expanded ? "Collapse" : "Expand"} Live Companion`}
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
          <small>Borderless-windowed mode required; this companion is not click-through.</small>
        </>
      ) : null}
    </aside>
  );
}

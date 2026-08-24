import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ChampSelectSnapshot } from "../api/types";
import { actionableErrorMessage } from "../api/client";
import { useEvents } from "../api/sse";
import { useLiveSession, useLiveStatus, usePack } from "../api/hooks";
import { pickHero } from "../components/champ-select/shared";
import { BanStrip, championLabel } from "../components/champ-select/BanStrip";
import { YourLaneCard } from "../components/champ-select/YourLaneCard";
import { MasteryCard } from "../components/champ-select/MasteryCard";
import { HowToPlayCard } from "../components/champ-select/HowToPlayCard";
import { SuggestedPicks } from "../components/champ-select/SuggestedPicks";
import { CompReadCard } from "../components/champ-select/CompReadCard";
import { LoadoutCard } from "../components/champ-select/LoadoutCard";
import { BanAdvisorCard } from "../components/champ-select/BanAdvisorCard";
import { YourSideCard } from "../components/champ-select/YourSideCard";
import { MatchStartCard } from "../components/champ-select/MatchStartCard";

function mmss(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Ticks the champ-select countdown down locally between SSE frames. */
function useCountdown(active: boolean, serverSeconds: number | null) {
  const base = useRef({ v: serverSeconds ?? 0, at: Date.now() });
  const [display, setDisplay] = useState(serverSeconds ?? 0);

  useEffect(() => {
    base.current = { v: serverSeconds ?? 0, at: Date.now() };
    setDisplay(serverSeconds ?? 0);
  }, [serverSeconds]);

  useEffect(() => {
    if (!active || serverSeconds == null) return;
    const id = setInterval(() => {
      setDisplay(Math.max(0, base.current.v - Math.floor((Date.now() - base.current.at) / 1000)));
    }, 500);
    return () => clearInterval(id);
  }, [active, serverSeconds == null]);

  return display;
}

export function ChampSelectPage() {
  const queryClient = useQueryClient();
  const sessionQuery = useLiveSession();
  const statusQuery = useLiveStatus();
  const packQuery = usePack();

  // Poll is primary; SSE champselect.state frames update the same cache the
  // moment the sidecar pushes them (fallback when a poll window misses a
  // transition).
  useEvents((msg) => {
    if (msg.type === "champselect.state") {
      queryClient.setQueryData<ChampSelectSnapshot>(
        ["live-session"],
        msg.data as ChampSelectSnapshot,
      );
    }
    if (msg.type === "pack.updated") {
      void queryClient.invalidateQueries({ queryKey: ["pack"] });
    }
  });

  const session = sessionQuery.data;
  const status = statusQuery.data;
  const active = !!session?.active;
  const timerSec = useCountdown(active, active ? (session?.timer_sec ?? null) : null);
  const hero = pickHero(packQuery.data);

  const localCell = session?.ally.find((cell) => cell.is_local);
  const localChampion =
    localCell && localCell.state === "picked" && localCell.champion_id
      ? championLabel(localCell.champion, localCell.champion_id)
      : null;
  const localTier =
    packQuery.data?.tier_list.find((entry) => entry.champion === localChampion)?.tier ?? null;

  return (
    <div
      style={{ fontFamily: "var(--font-mono)", letterSpacing: "-.01em", minWidth: 0 }}
      data-testid="champ-select-page"
    >
      <BanStrip
        snapshot={session}
        timerLabel={mmss(timerSec)}
        lastError={status?.last_error ?? null}
      />
      {packQuery.isError && (
        <div style={{ paddingTop: 10, fontSize: 10.5, color: "var(--color-danger)" }}>
          {actionableErrorMessage(packQuery.error, "pack")}
        </div>
      )}

      <div
        className="champ-select-layout"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 368px) minmax(0, 1fr) minmax(0, 316px)",
          gap: 14,
          paddingTop: 14,
          minWidth: 0,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 11, minHeight: 0, minWidth: 0 }}>
          <YourLaneCard champion={localChampion} tier={localTier} />
          <MasteryCard pack={packQuery.data} />
          <HowToPlayCard />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0, minWidth: 0 }}>
          <SuggestedPicks pack={packQuery.data} />
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
              gap: 12,
              flex: 1,
              minHeight: 0,
              minWidth: 0,
            }}
          >
            <CompReadCard />
            <LoadoutCard />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0, minWidth: 0 }}>
          <BanAdvisorCard pack={packQuery.data} />
          <YourSideCard session={session} />
          <MatchStartCard active={active} pick={hero?.champion} />
        </div>
      </div>
    </div>
  );
}

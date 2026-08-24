import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { LiveStatus } from "../api/types";
import { useEvents } from "../api/sse";
import {
  ActivePlayerCard,
  CheatSheetCard,
  clockLabel,
  DeadNowCard,
  EnemySpellsCard,
  EventFeedCard,
  ItemValueCard,
  ObjectivesCard,
  PlayerList,
  RightNowCard,
  TeamVsTeamCard,
  WinProbabilityCard,
} from "../components/live-match";

/** Ticks locally between server/SSE updates so the clock advances every second. */
function useGameClock(active: boolean, serverClockS: number) {
  const base = useRef({ v: serverClockS, at: Date.now() });
  const [display, setDisplay] = useState(serverClockS);

  useEffect(() => {
    base.current = { v: serverClockS, at: Date.now() };
    setDisplay(serverClockS);
  }, [serverClockS]);

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      setDisplay(base.current.v + Math.floor((Date.now() - base.current.at) / 1000));
    }, 500);
    return () => clearInterval(id);
  }, [active]);

  return display;
}

export function LiveMatchPage() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["live-status"],
    queryFn: api.liveStatus,
    refetchInterval: 3000,
  });
  const packQuery = useQuery({ queryKey: ["pack"], queryFn: api.pack });

  useEvents((msg) => {
    if (msg.type === "live.state") {
      queryClient.setQueryData<LiveStatus>(["live-status"], msg.data as LiveStatus);
    }
    if (msg.type === "pack.updated") {
      void queryClient.invalidateQueries({ queryKey: ["pack"] });
    }
  });

  const status = statusQuery.data;
  const active = status?.ingame.active ?? false;
  const clockS = useGameClock(active, status?.ingame.clock_s ?? 0);

  return (
    <div
      style={{
        margin: "0 -14px -14px",
        padding: "12px 14px 14px",
        minHeight: "100%",
        display: "flex",
        flexDirection: "column",
        background: "radial-gradient(120% 80% at 20% 0%,#151831,var(--color-bg) 60%)",
      }}
    >
      <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 7, marginBottom: 10 }}>
        <span
          className="pill mono-n"
          data-testid="bridge-status"
          style={
            active
              ? {
                  background: "var(--color-teal-low)",
                  color: "var(--color-teal)",
                  boxShadow: "var(--shadow-z1)",
                }
              : {
                  background: "var(--color-amber-low)",
                  color: "var(--color-amber)",
                  boxShadow: "var(--shadow-z1)",
                }
          }
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: 999,
              background: active ? "var(--color-teal)" : "var(--color-amber)",
              boxShadow: active ? "0 0 8px var(--color-teal)" : "none",
            }}
          />
          {active ? ":2999 · 1s poll" : "waiting for :2999"}
        </span>
        <div
          className="pill"
          style={{ background: "var(--color-info-low)", color: "#cfe3f9", boxShadow: "var(--shadow-z1)" }}
        >
          <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-info)" }} />
          Findings Pack v1
        </div>
        <div
          className="pill mono-n"
          data-testid="game-clock"
          style={{
            marginLeft: "auto",
            background: "var(--color-surface-3)",
            color: "var(--color-text)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          {clockLabel(clockS)}
        </div>
      </div>

      <PlayerList active={active} />

      <div
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "356px 1fr 320px",
          gap: 14,
          paddingTop: 14,
          minHeight: 0,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
          <ActivePlayerCard />
          <CheatSheetCard />
          <RightNowCard pack={packQuery.data} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <WinProbabilityCard pack={packQuery.data} clockS={clockS} active={active} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <TeamVsTeamCard pack={packQuery.data} />
            <EventFeedCard />
          </div>
          <ItemValueCard />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <DeadNowCard />
          <ObjectivesCard pack={packQuery.data} />
          <EnemySpellsCard />
        </div>
      </div>
    </div>
  );
}

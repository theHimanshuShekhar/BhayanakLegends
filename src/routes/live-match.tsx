import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { actionableErrorMessage, api } from "../api/client";
import { useGameClock, useGameClockSource } from "../api/clock";
import type { FindingsPack, InGameSnapshot, PlayerLive } from "../api/types";
import { useEvents } from "../api/sse";
import { useLiveIngame } from "../api/hooks";
import {
  ActivePlayerCard,
  CheatSheetCard,
  clockLabel,
  EventFeedCard,
  ItemsByPlayerCard,
  ObjectivesCard,
  PlayerList,
  RightNowCard,
  TeamVsTeamCard,
  WinProbabilityCard,
} from "../components/live-match";
import { PageHeader } from "../components/Layout";

function GameClockSource({ active, serverClock }: { active: boolean; serverClock: number }) {
  useGameClockSource(active, serverClock);
  return null;
}

function GameClockDisplay() {
  const clockS = useGameClock();
  return (
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
  );
}

function LiveWinProbabilityCard({
  pack,
  active,
  packVersion,
}: {
  pack: FindingsPack | undefined;
  active: boolean;
  packVersion: string | null;
}) {
  const clockS = useGameClock();
  return <WinProbabilityCard pack={pack} clockS={clockS} active={active} packVersion={packVersion} />;
}

function findLocalPlayer(snapshot: InGameSnapshot | undefined): PlayerLive | null {
  if (!snapshot?.local_summoner) return null;
  const all = [...snapshot.teams.order, ...snapshot.teams.chaos];
  return all.find((p) => p.summoner === snapshot.local_summoner) ?? null;
}
function isRenderableSnapshot(value: unknown): value is InGameSnapshot {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const snapshot = value as Record<string, unknown>;
  const teams = snapshot.teams;
  if (typeof teams !== "object" || teams === null || Array.isArray(teams)) return false;
  const teamRecord = teams as Record<string, unknown>;
  const isNullableString = (candidate: unknown) => candidate === null || typeof candidate === "string";
  const isPlayer = (candidate: unknown) => {
    if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) return false;
    const player = candidate as Record<string, unknown>;
    return (
      typeof player.summoner === "string" &&
      isNullableString(player.champion) &&
      ["level", "kills", "deaths", "assists", "cs", "ward_score"].every(
        (key) => typeof player[key] === "number" && Number.isFinite(player[key]),
      ) &&
      Array.isArray(player.items) &&
      player.items.every(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          !Array.isArray(item) &&
          Number.isInteger((item as Record<string, unknown>).id) &&
          Number.isInteger((item as Record<string, unknown>).count),
      )
    );
  };
  const isEvent = (candidate: unknown) => {
    if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) return false;
    const event = candidate as Record<string, unknown>;
    return (
      typeof event.name === "string" &&
      typeof event.t_s === "number" &&
      Number.isFinite(event.t_s) &&
      isNullableString(event.actor) &&
      isNullableString(event.victim) &&
      isNullableString(event.detail)
    );
  };
  return (
    typeof snapshot.active === "boolean" &&
    typeof snapshot.clock_s === "number" &&
    Number.isFinite(snapshot.clock_s) &&
    (snapshot.mode === null || typeof snapshot.mode === "string") &&
    isNullableString(snapshot.local_summoner) &&
    isNullableString(snapshot.local_champion) &&
    Array.isArray(teamRecord.order) &&
    teamRecord.order.every(isPlayer) &&
    Array.isArray(teamRecord.chaos) &&
    teamRecord.chaos.every(isPlayer) &&
    Array.isArray(snapshot.events) &&
    snapshot.events.every(isEvent)
  );
}

export function LiveMatchPage() {
  const queryClient = useQueryClient();
  const ingameQuery = useLiveIngame();
  const packQuery = useQuery({ queryKey: ["pack"], queryFn: api.pack });
  const [activePackVersion, setActivePackVersion] = useState<string | null>(null);
  const [liveFrame, setLiveFrame] = useState<{ snapshot?: InGameSnapshot; hidden: boolean } | null>(null);
  const hadLiveConnection = useRef(false);
  const liveEventsConnected = useEvents((msg) => {
    if (msg.type === "live.state") {
      if (isRenderableSnapshot(msg.data)) {
        setLiveFrame({ snapshot: msg.data, hidden: false });
        queryClient.setQueryData(["live-ingame"], msg.data);
      } else {
        setLiveFrame({ hidden: true });
      }
    }
    if (msg.type === "hello") {
      const version = msg.data.pack_version;
      if (version !== null && (typeof version !== "string" || version.trim().length === 0)) return;
      setActivePackVersion(version);
    }
    if (msg.type === "pack.updated") {
      if (!Number.isInteger(msg.data.schema_version)) return;
      if (typeof msg.data.pack_version !== "string" || msg.data.pack_version.trim().length === 0) return;
      setActivePackVersion(msg.data.pack_version);
      void queryClient.invalidateQueries({ queryKey: ["pack"] });
    }
  });

  useEffect(() => {
    if (liveEventsConnected) {
      hadLiveConnection.current = true;
    } else if (hadLiveConnection.current) {
      setLiveFrame({ hidden: true });
    }
  }, [liveEventsConnected]);

  useEffect(() => {
    if (!packQuery.isSuccess) return;
    const version = packQuery.data?.pack_version;
    setActivePackVersion(typeof version === "string" && version.trim().length > 0 ? version : null);
  }, [packQuery.data, packQuery.isSuccess]);
  const renderPack =
    activePackVersion !== null && packQuery.data?.pack_version === activePackVersion ? packQuery.data : undefined;

  const querySnapshot = ingameQuery.isError ? undefined : ingameQuery.data;
  const ingame = ingameQuery.isError || liveFrame?.hidden ? undefined : (liveFrame?.snapshot ?? querySnapshot);
  const active = ingame?.active === true;
  const liveStatus = ingameQuery.isError ? "error" : active ? "active" : "waiting";




  return (
    <div
      className="live-match-layout"
      role="region"
      aria-label="Live Companion: In Game"
      aria-busy={ingameQuery.isLoading || packQuery.isLoading}
      style={{
        margin: "0 -14px -14px",
        padding: "12px 14px 14px",
        minHeight: "100%",
        display: "flex",
        flexDirection: "column",
        background: "radial-gradient(120% 80% at 20% 0%,#151831,var(--color-bg) 60%)",
      }}
    >
      <PageHeader title="Live Companion: In Game" />
      {liveStatus === "error" ? (
        <div role="alert" data-testid="ingame-error" aria-live="assertive" style={{ margin: "0 0 10px", fontSize: 10.5, color: "var(--color-amber)" }}>
          {actionableErrorMessage(ingameQuery.error)}
        </div>
      ) : (
        <p
          role="status"
          aria-live="polite"
          data-testid="live-route-status"
          style={{ margin: "0 0 10px", fontSize: 10, color: active ? "var(--color-teal)" : "var(--color-dim)" }}
        >
          {active ? "Live Companion game data active" : "Waiting for Live Companion game data"}
        </p>
      )}
      <GameClockSource active={active} serverClock={ingame?.clock_s ?? 0} />
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
                  background: "var(--color-surface-3)",
                  color: "var(--color-dimmer)",
                  boxShadow: "var(--shadow-z1)",
                }
          }
        >
          <span
            data-testid="bridge-dot"
            style={{
              width: 6,
              height: 6,
              borderRadius: 999,
              background: active ? "var(--color-teal)" : "var(--color-dimmer)",
              boxShadow: active ? "0 0 8px var(--color-teal)" : "none",
            }}
          />
          {active ? ":2999 · 1s poll" : "Live Companion idle"}
        </span>
        {ingame?.mode && (
          <div
            className="pill mono-n"
            data-testid="game-mode"
            style={{ background: "var(--color-surface-3)", color: "var(--color-dim)", boxShadow: "var(--shadow-z1)" }}
          >
            {ingame.mode}
          </div>
        )}
        <div
          className="pill"
          style={{ background: "var(--color-info-low)", color: "#cfe3f9", boxShadow: "var(--shadow-z1)" }}
        >
          <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-info)" }} />
          Findings Pack{activePackVersion ? ` ${activePackVersion}` : ""}
        </div>
        <GameClockDisplay />
      </div>
      {packQuery.isError && (
        <div role="alert" style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
          {actionableErrorMessage(packQuery.error, "pack")}
        </div>
      )}

      <PlayerList snapshot={ingame} />

      <div
        className="live-match-columns"
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "356px 1fr 320px",
          gap: 14,
          paddingTop: 14,
          minHeight: 0,
        }}
      >
        <div className="live-match-column" style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
          <ActivePlayerCard player={findLocalPlayer(ingame)} />
          <CheatSheetCard />
          <RightNowCard pack={renderPack} />
        </div>

        <div className="live-match-column" style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <LiveWinProbabilityCard pack={renderPack} active={active} packVersion={activePackVersion} />
          <div className="live-match-middle-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <TeamVsTeamCard snapshot={ingame} />
            <EventFeedCard snapshot={ingame} />
          </div>
          <ItemsByPlayerCard snapshot={ingame} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
          <ObjectivesCard pack={renderPack} />
        </div>
      </div>
    </div>
  );
}

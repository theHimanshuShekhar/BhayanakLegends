import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FindingsPack, LiveStatus } from "../api/types";
import { useEvents } from "../api/sse";
import {
  EventFeed,
  HabitNudges,
  LanesAheadMeter,
  ObjectiveCard,
  WpBand,
} from "../components/live";
import { EmptyState, pct } from "../components/ui";
import { PageHeader } from "../components/Layout";

function pp(v: number | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}pp`;
}

function gold(deficit: number): string {
  return `${deficit.toLocaleString("en-US")}g`;
}

function clockLabel(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

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

function ObjectivesPriors({ pack }: { pack: FindingsPack | undefined }) {
  const o = pack?.objectives;
  const lanesAhead = pack?.findings.find((f) => f.key === "lanes_ahead");
  return (
    <section className="space-y-4" data-testid="objectives-priors">
      <div className="text-[10px] uppercase tracking-widest text-dimmer">Objectives priors</div>
      <div className="grid gap-4 md:grid-cols-3">
        <ObjectiveCard
          objective="Baron"
          headline="Comeback tool"
          stats={[
            { label: "pre-25 win rate", value: pct(o?.baron_pre25_win_rate) },
            { label: "comeback lift", value: pp(o?.baron_comeback_lift_pp) },
          ]}
          // Actionable per pack tier: may instruct.
          actionable
          takeaway="Trailing teams that secure Baron flip games — treat it as the comeback lever, not a lead extender."
        />
        <ObjectiveCard
          objective="Dragon"
          headline="Checkpoint, not weapon"
          stats={[
            { label: "denial win rate", value: pct(o?.dragon_denial_win_rate) },
            { label: "first before 20", value: pct(o?.first_dragon_pre20_win_rate) },
          ]}
          takeaway="Denying the enemy's dragons outvalues forcing risky ones."
        />
        <ObjectiveCard
          objective="Herald"
          headline="Early tempo"
          stats={[{ label: "before 20 min", value: pct(o?.herald_pre20_win_rate) }]}
          takeaway="Its window closes at 20 minutes."
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-line bg-surface p-4 shadow-z1" data-testid="card-comeback-odds">
          <div className="text-[10px] uppercase tracking-widest text-accent">Comeback odds</div>
          <h2 className="mt-0.5 text-sm font-medium">Gold down at 15 → win chance</h2>
          {(pack?.comeback_odds ?? []).length === 0 ? (
            <p className="mt-3 text-xs text-dim">Comeback table arrives with the next Findings Pack.</p>
          ) : (
            <table className="mt-3 w-full text-left">
              <thead>
                <tr className="text-[10px] uppercase tracking-widest text-dimmer">
                  <th className="pb-1 font-normal">Gold deficit</th>
                  <th className="pb-1 text-right font-normal">Win chance</th>
                </tr>
              </thead>
              <tbody>
                {(pack?.comeback_odds ?? []).map((row) => (
                  <tr key={row.gold_deficit_at_15} data-testid={`comeback-row-${row.gold_deficit_at_15}`} className="border-t border-line">
                    <td className="py-1.5 font-mono text-xs">{gold(row.gold_deficit_at_15)}</td>
                    <td className="py-1.5 text-right font-mono text-xs">{pct(row.win_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-3 text-[10px] leading-relaxed text-dimmer">
            Survivorship bias documented; surrender advisor model ships with the next Findings Pack.
          </p>
        </section>

        <section className="rounded-lg border border-line bg-surface p-4 shadow-z1" data-testid="card-lanes-ahead">
          <div className="text-[10px] uppercase tracking-widest text-accent">Lanes ahead</div>
          <h2 className="mt-0.5 mb-3 text-sm font-medium">How the curve moves</h2>
          <LanesAheadMeter finding={lanesAhead} />
          {!lanesAhead && (
            <p className="text-xs text-dim">Lanes-ahead finding arrives with the next Findings Pack.</p>
          )}
        </section>
      </div>
    </section>
  );
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
    <div>
      <PageHeader kicker="Live companion" title="Live Match" />

      {!active ? (
        <div className="max-w-xl space-y-4">
          <EmptyState
            title=":2999 comes online at match start"
            body="Win-probability guidance appears once the Live Client Data API is reachable. Borderless-windowed mode required for the widget experience."
          />
        </div>
      ) : (
        <div className="space-y-4">
          <header className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3 shadow-z1">
            <div className="flex items-center gap-2" data-testid="score-strip">
              <span className="size-2 rounded-full bg-accent" aria-hidden />
              <span className="font-mono text-sm">0</span>
              <span className="text-[10px] uppercase tracking-widest text-dimmer">blue vs red</span>
              <span className="font-mono text-sm">0</span>
              <span className="size-2 rounded-full bg-danger" aria-hidden />
              {/* Placeholder strip until the LCU bridge exposes team scores. */}
            </div>
            <div className="flex items-baseline gap-2">
              {status?.ingame.mode && (
                <span className="text-[10px] uppercase tracking-widest text-dimmer">{status.ingame.mode}</span>
              )}
              <span className="font-mono text-xl" data-testid="game-clock">
                {clockLabel(clockS)}
              </span>
            </div>
          </header>

          <div className="grid gap-4 lg:grid-cols-[1fr_minmax(260px,340px)]">
            <div className="space-y-4">
              <WpBand pack={packQuery.data} clockS={clockS} />
              <EventFeed />
            </div>
            <HabitNudges habits={packQuery.data?.habits ?? []} />
          </div>
        </div>
      )}

      {/* The objectives priors board is always visible — it works without a live game. */}
      <div className={active ? "mt-6" : ""}>
        <ObjectivesPriors pack={packQuery.data} />
      </div>
    </div>
  );
}

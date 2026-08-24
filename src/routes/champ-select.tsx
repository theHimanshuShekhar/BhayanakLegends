import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FindingsPack, LiveStatus, TierEntry } from "../api/types";
import { useEvents } from "../api/sse";
import { BanAdvisorCard, MatchupHonestyCard, TeamSlots } from "../components/live";
import { EmptyState, pct } from "../components/ui";
import { PageHeader } from "../components/Layout";

const ROLE_SELECTOR = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"] as const;

function byWinRate(a: TierEntry, b: TierEntry) {
  return b.win_rate - a.win_rate;
}

interface SuggestedPick {
  slot: string;
  champion: string;
  winRate: number;
  basis: string;
}

function suggestedPicks(entries: TierEntry[]): SuggestedPick[] {
  const picks: SuggestedPick[] = [];
  // Basis labels state the population statistic behind each suggestion so the
  // caption stays honest: these are pack-level suggestions, not personal ones.
  const best = entries.filter((e) => e.tier === "S" || e.tier === "A").sort(byWinRate)[0];
  if (best) picks.push({ slot: "Best pick", champion: best.champion, winRate: best.win_rate, basis: "highest S/A win rate" });
  const pocket = [...entries].sort(byWinRate)[0];
  if (pocket) picks.push({ slot: "Pocket pick", champion: pocket.champion, winRate: pocket.win_rate, basis: "highest win rate in pool" });
  const comfort = [...entries].sort((a, b) => b.pick_rate - a.pick_rate)[0];
  if (comfort) picks.push({ slot: "Comfort pick", champion: comfort.champion, winRate: comfort.win_rate, basis: "highest pick rate" });
  return picks;
}

function PoolCard({ pack }: { pack: FindingsPack | undefined }) {
  const [role, setRole] = useState<string>("MIDDLE");
  const entries = (pack?.tier_list ?? []).filter((t) => t.role === role);
  const picks = suggestedPicks(entries);
  return (
    <section className="rounded-lg border border-line bg-surface p-4 shadow-z1" data-testid="card-your-pool">
      <div className="text-[10px] uppercase tracking-widest text-accent">Your pool</div>
      <h2 className="mt-0.5 text-sm font-medium">Suggested picks</h2>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {ROLE_SELECTOR.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setRole(r)}
            className={`rounded-md border px-2 py-1 text-[10px] uppercase tracking-widest ${
              r === role
                ? "border-accent text-accent"
                : "border-line text-dim hover:text-text"
            }`}
          >
            {r}
          </button>
        ))}
      </div>
      <ul className="mt-4 space-y-3">
        {picks.map((p) => (
          <li key={p.slot} className="border-t border-line pt-2.5 first:border-t-0 first:pt-0">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10px] uppercase tracking-widest text-dimmer">{p.slot}</span>
              <span className="font-mono text-xs text-teal">{pct(p.winRate)}</span>
            </div>
            <div className="text-sm font-medium">{p.champion}</div>
            <div className="text-[11px] text-dim">by {p.basis}</div>
          </li>
        ))}
        {picks.length === 0 && (
          <li className="text-xs text-dim">No tier-list rows for this role yet.</li>
        )}
      </ul>
      <p className="mt-4 border-t border-line pt-2.5 text-[10px] leading-relaxed text-dimmer">
        Population-level suggestions from the Findings Pack — not your history.
      </p>
    </section>
  );
}

export function ChampSelectPage() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["live-status"],
    queryFn: api.liveStatus,
    refetchInterval: 3000,
  });
  const packQuery = useQuery({ queryKey: ["pack"], queryFn: api.pack });

  // Poll is primary; SSE live.state frames update the same cache the moment
  // the sidecar pushes them (fallback when a poll window misses a transition).
  useEvents((msg) => {
    if (msg.type === "live.state") {
      queryClient.setQueryData<LiveStatus>(["live-status"], msg.data as LiveStatus);
    }
    if (msg.type === "pack.updated") {
      void queryClient.invalidateQueries({ queryKey: ["pack"] });
    }
  });

  const status = statusQuery.data;
  const active = status?.champ_select.active ?? false;
  const phase = status?.champ_select.phase ?? null;

  return (
    <div>
      <PageHeader kicker="Live companion" title="Champ Select" />

      <div className="space-y-4">
        {!active && (
          <div className="max-w-xl">
            <EmptyState
              title="Waiting for champ select"
              body="The app detects the League client automatically. Ranked enemy names stay hidden by policy."
            />
            {status?.last_error && (
              <p className="mt-3 text-xs text-amber" data-testid="detection-status">
                client detection: {status.last_error}
              </p>
            )}
          </div>
        )}
        {active && (
          <>
            {/* Ally slots show roles + session phase; per-player summoner names are
                not available at v1. Enemy slots are hard-coded to role + ??? —
                COMPLIANCE: no enemy summoner names/tags ever render here. */}
            <TeamSlots side="ally" phase={phase} />
            <TeamSlots side="enemy" phase={null} />
          </>
        )}

        <div
          className={`grid gap-4 ${active ? "lg:grid-cols-[minmax(240px,300px)_1fr_minmax(280px,340px)]" : "lg:grid-cols-3"}`}
        >
          <PoolCard pack={packQuery.data} />
          <BanAdvisorCard pack={packQuery.data} />
          <MatchupHonestyCard pack={packQuery.data} />
        </div>
      </div>
    </div>
  );
}

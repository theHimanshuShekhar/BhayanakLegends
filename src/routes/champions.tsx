import { useMemo, useState } from "react";
import { usePack } from "../api/hooks";
import "../components/journal/kicker.css";
import { PageHeader } from "../components/Layout";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { Card, Tag, pct } from "../components/ui";
import type { FindingTier, MatchupExample, TierEntry } from "../api/types";

const TIER_STYLES: Record<TierEntry["tier"], string> = {
  S: "bg-teal-low text-teal",
  A: "bg-accent-low text-accent",
  B: "bg-info-low text-info",
  C: "bg-surface-3 text-dim",
};

const TIER_ORDER = { S: 0, A: 1, B: 2, C: 3 };

function Chip({
  active,
  onClick,
  children,
  testid,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
  testid: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={`rounded-full border px-3 py-1 text-[10px] font-medium uppercase tracking-widest transition-colors ${
        active
          ? "border-accent bg-accent-low text-accent"
          : "border-line text-dim hover:border-dim hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

function TierBadge({ tier }: { tier: TierEntry["tier"] }) {
  return (
    <span
      className={`inline-flex size-5 items-center justify-center rounded font-mono text-[10px] font-medium ${TIER_STYLES[tier]}`}
    >
      {tier}
    </span>
  );
}

const COMP_FINDING_RE = /(comp|damage|fit)/i;

export function ChampionsPage() {
  const pack = usePack();
  const [role, setRole] = useState<string>("ALL");

  const roles = useMemo(() => {
    const set = new Set<string>();
    for (const t of pack.data?.tier_list ?? []) set.add(t.role);
    return [...set].sort();
  }, [pack.data]);

  const tierRows = useMemo(() => {
    const all = pack.data?.tier_list ?? [];
    const inRole = role === "ALL" ? all : all.filter((t) => t.role === role);
    return [...inRole].sort(
      (a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier] || b.win_rate - a.win_rate,
    );
  }, [pack.data, role]);

  const matchups = useMemo(() => {
    const all = pack.data?.matchup_examples ?? [];
    return role === "ALL" ? all : all.filter((m) => m.role === role);
  }, [pack.data, role]);

  const youCounter = matchups.filter((m) => m.wr >= 0.5);
  const countersYou = matchups.filter((m) => m.wr < 0.5);

  const compFindings = useMemo(
    () =>
      (pack.data?.findings ?? []).filter(
        (f) => COMP_FINDING_RE.test(f.key) || COMP_FINDING_RE.test(f.title),
      ),
    [pack.data],
  );

  function tierTag(tier: FindingTier) {
    if (tier === "diagnostic") return <Tag verdict="neutral">diagnostic</Tag>;
    return <Tag verdict="advice">advice</Tag>;
  }

  function MatchupRow({ m }: { m: MatchupExample }) {
    return (
      <li className="flex items-center justify-between gap-3 border-b border-line py-2 last:border-b-0">
        <div>
          <span className="text-xs">{m.champion}</span>
          <span className="ml-2 text-[10px] uppercase tracking-widest text-dimmer">vs</span>
          <span className="ml-2 text-xs text-dim">{m.opponent}</span>
        </div>
        <span className="font-mono text-xs text-dim">{m.games}g</span>
        <span className="font-mono text-xs">
          {pct(m.wr)} ±{m.ci.toFixed(1)}
        </span>
      </li>
    );
  }

  return (
    <div>
      <PageHeader kicker="Improvement Journal" title="Champions" />

      <div className="mb-4 flex flex-wrap gap-2" data-testid="role-chips">
        <Chip active={role === "ALL"} onClick={() => setRole("ALL")} testid="role-ALL">
          All
        </Chip>
        {roles.map((r) => (
          <Chip key={r} active={role === r} onClick={() => setRole(r)} testid={`role-${r}`}>
            {r}
          </Chip>
        ))}
      </div>

      {pack.isLoading && <div className="text-xs text-dim">loading…</div>}
      {pack.isError && (
        <div className="text-xs text-danger">Findings Pack unavailable — sidecar offline.</div>
      )}

      {pack.data && (
        <div className="space-y-4">
          <Card kicker={`Tier list · ${role.toLowerCase()}`} title="Where your friends' games land">
            <ul data-testid="tier-list">
              {tierRows.map((t) => (
                <li
                  key={`${t.champion}-${t.role}`}
                  className="flex items-center gap-3 border-b border-line py-2 last:border-b-0"
                >
                  <TierBadge tier={t.tier} />
                  <span className="text-xs">{t.champion}</span>
                  <span className="ml-auto font-mono text-xs text-dim">{pct(t.pick_rate)}</span>
                  <span className="w-14 text-right font-mono text-xs">{pct(t.win_rate)}</span>
                  <span className="w-12 text-right font-mono text-[10px] text-dimmer">
                    {t.games}g
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card
            kicker="Diagnostic · describes, never advises"
            title="Trap picks"
            className="border-danger/40"
          >
            <p className="mb-2 text-xs text-dim">
              Looks strong, isn't — popular in drafts while their win rate sits below even.
            </p>
            <ul data-testid="trap-picks-list">
              {(pack.data.trap_picks ?? []).map((tp) => (
                <li key={tp.champion} className="flex items-center gap-3 py-1.5">
                  <span className="inline-block size-1.5 rounded-full bg-danger" />
                  <span className="text-xs">{tp.champion}</span>
                  <span className="ml-auto font-mono text-xs text-danger">
                    {pct(tp.win_rate)} WR
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card kicker="Matchups" title="Counters, both directions">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <div className="mb-1 text-[10px] uppercase tracking-widest text-teal">
                  You counter
                </div>
                <ul data-testid="you-counter-list">
                  {youCounter.map((m) => (
                    <MatchupRow key={`${m.champion}-${m.opponent}`} m={m} />
                  ))}
                  {youCounter.length === 0 && (
                    <li className="py-1 text-xs text-dimmer">no clear edges in the pack</li>
                  )}
                </ul>
              </div>
              <div>
                <div className="mb-1 text-[10px] uppercase tracking-widest text-danger">
                  Counters you
                </div>
                <ul data-testid="counters-you-list">
                  {countersYou.map((m) => (
                    <MatchupRow key={`${m.champion}-${m.opponent}`} m={m} />
                  ))}
                  {countersYou.length === 0 && (
                    <li className="py-1 text-xs text-dimmer">no rough spots in the pack</li>
                  )}
                </ul>
              </div>
            </div>
          </Card>

          {compFindings.length > 0 && (
            <Card kicker="Comp advice" title="From the Findings Pack">
              <ul data-testid="comp-findings" className="space-y-3">
                {compFindings.map((f) => (
                  <li key={f.key} className="flex flex-wrap items-center gap-2">
                    {tierTag(f.tier)}
                    <span className="text-xs">{f.statement}</span>
                    {f.value != null && (
                      <span className="ml-auto font-mono text-xs text-dim">
                        {f.value > 0 ? "+" : ""}
                        {f.value}
                        {f.unit === "pp" ? " pp" : ""}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <CaveatFooter />
        </div>
      )}
    </div>
  );
}

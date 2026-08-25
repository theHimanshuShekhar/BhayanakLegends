import { useMemo, useState } from "react";
import { usePack, usePatchAggregates, useTrajectories } from "../api/hooks";
import { actionableErrorMessage } from "../api/client";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { ChampionHeader } from "../components/champions/ChampionHeader";
import { RoleChips } from "../components/champions/RoleChips";
import { MatchupsCard } from "../components/champions/MatchupsCard";
import { RoleTierList, sortTierRows } from "../components/champions/RoleTierList";
import { BuildOrderCard } from "../components/champions/BuildOrderCard";
import { TrajectoryCard } from "../components/champions/TrajectoryCard";
import { CompCard, DamageFitCard, GoldWasteCard } from "../components/champions/CompFitCards";
import { PageHeader } from "../components/Layout";

const COMP_RE = /comp/i;
const DAMAGE_FIT_RE = /damage[-_]?fit/i;
const GOLD_WASTE_RE = /gold[-_]?waste/i;


export function ChampionsPage() {
  const pack = usePack();
  const [activeRoleState, setActiveRole] = useState<string | null>(null);
  const [selectedChampion, setSelectedChampion] = useState<string | null>(null);

  const roles = useMemo(() => {
    const set = new Set<string>();
    for (const t of pack.data?.tier_list ?? []) set.add(t.role);
    return [...set].sort();
  }, [pack.data]);

  const activeRole =
    activeRoleState ?? (roles.includes("MIDDLE") ? "MIDDLE" : (roles[0] ?? null));
  const trajectoryFilters = {
    role: activeRole ?? undefined,
    champion: selectedChampion ?? undefined,
  };
  const trajectoryEnabled = Boolean(pack.data && activeRole && selectedChampion);
  const trajectories = useTrajectories(trajectoryFilters, { enabled: trajectoryEnabled });
  const aggregates = usePatchAggregates(trajectoryFilters, { enabled: trajectoryEnabled });

  const headerEntry = useMemo(
    () =>
      pack.data?.tier_list.find(
        (t) => t.role === activeRole && t.champion === selectedChampion,
      ) ?? null,
    [pack.data, activeRole, selectedChampion],
  );

  const banRates = useMemo(
    () => new Map((pack.data?.ban_advisor ?? []).map((b) => [b.champion, b.ban_rate])),
    [pack.data],
  );

  const tierRows = useMemo(
    () => sortTierRows((pack.data?.tier_list ?? []).filter((t) => t.role === activeRole)),
    [pack.data, activeRole],
  );

  const matchups = useMemo(
    () =>
      (pack.data?.matchup_examples ?? []).filter(
        (m) =>
          m.role === activeRole &&
          m.champion === selectedChampion &&
          m.opponent !== selectedChampion,
      ),
    [pack.data, activeRole, selectedChampion],
  );

  const trapPicks = useMemo(
    () => new Set((pack.data?.trap_picks ?? []).map((t) => t.champion)),
    [pack.data],
  );

  const compFindings = useMemo(
    () =>
      (pack.data?.findings ?? []).filter(
        (f) => COMP_RE.test(f.key) || COMP_RE.test(f.title),
      ),
    [pack.data],
  );
  const damageFit = useMemo(
    () => (pack.data?.findings ?? []).find((f) => DAMAGE_FIT_RE.test(f.key)) ?? null,
    [pack.data],
  );
  const goldWaste = useMemo(
    () => (pack.data?.findings ?? []).find((f) => GOLD_WASTE_RE.test(f.key)) ?? null,
    [pack.data],
  );

  function selectRole(role: string) {
    setActiveRole(role);
    setSelectedChampion(null);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 14 }}>
      <PageHeader title="Champion Evidence" />
      {roles.length > 0 && (
        <RoleChips roles={roles} active={activeRole} onSelect={selectRole} />
      )}
      <div
        role="status"
        aria-live="polite"
        style={{ minHeight: 15, fontSize: 10.5, color: "var(--color-dim)" }}
      >
        {selectedChampion
          ? `${selectedChampion} selected for ${activeRole}`
          : "Select a champion from the role tier list."}
      </div>

      {pack.isLoading && (
        <div style={{ fontSize: 10.5, color: "var(--color-dim)" }}>loading…</div>
      )}
      {pack.isError && (
        <div style={{ fontSize: 10.5, color: "var(--color-danger)" }}>
          {actionableErrorMessage(pack.error, "pack")}
        </div>
      )}

      {pack.data && activeRole && (
        <div
          style={{
            minHeight: 0,
            display: "grid",
            gridTemplateColumns: "380px 1fr 360px",
            gap: 14,
            alignItems: "start",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
            {headerEntry && (
              <ChampionHeader
                entry={headerEntry}
                banRate={banRates.get(headerEntry.champion) ?? null}
              />
            )}
            <MatchupsCard champion={selectedChampion} matchups={matchups} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
            {compFindings.length > 0 && <CompCard findings={compFindings} />}
            {damageFit && <DamageFitCard finding={damageFit} />}
            <RoleTierList
              role={activeRole}
              rows={tierRows}
              trapPicks={trapPicks}
              selectedChampion={selectedChampion}
              onSelect={setSelectedChampion}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
            <BuildOrderCard />
            <TrajectoryCard
              champion={selectedChampion}
              points={trajectories.data ?? []}
              aggregates={aggregates.data ?? []}
              trajectoryLoading={trajectories.isLoading}
              trajectoryError={
                trajectories.isError ? actionableErrorMessage(trajectories.error) : null
              }
              aggregateError={
                aggregates.isError ? actionableErrorMessage(aggregates.error) : null
              }
            />
            {goldWaste && <GoldWasteCard finding={goldWaste} />}
          </div>
        </div>
      )}

      {pack.data && <CaveatFooter />}
    </div>
  );
}

import { useMemo, useState } from "react";
import { actionableErrorMessage } from "../api/client";
import { usePack, usePatchAggregates, useTrajectories } from "../api/hooks";
import { isFindingsPack, isFindingsPackV2 } from "../api/pack-v2";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { ChampionHeader } from "../components/champions/ChampionHeader";
import { RoleChips } from "../components/champions/RoleChips";
import { MatchupsCard } from "../components/champions/MatchupsCard";
import { RoleTierList } from "../components/champions/RoleTierList";
import { BuildOrderCard } from "../components/champions/BuildOrderCard";
import { RouteArchetypesCard } from "../components/champions/RouteArchetypesCard";
import { TrajectoryCard } from "../components/champions/TrajectoryCard";
import { CompCard, DamageFitCard, GoldWasteCard } from "../components/champions/CompFitCards";
import {
  findingEvidence,
  matchupEvidence,
  tierEvidence,
} from "../components/populationEvidence";
import { PageHeader } from "../components/Layout";

const COMP_RE = /comp/i;
const DAMAGE_FIT_RE = /damage[-_]?fit/i;
const GOLD_WASTE_RE = /gold[-_]?waste/i;


export function ChampionsPage() {
  const pack = usePack();
  const packEvidence = isFindingsPack(pack.data) ? pack.data : undefined;
  const packV2 = isFindingsPackV2(packEvidence) ? packEvidence : undefined;
  const [activeRoleState, setActiveRole] = useState<string | null>(null);
  const [selectedChampion, setSelectedChampion] = useState<string | null>(null);
  const populationTiers = useMemo(() => tierEvidence(packEvidence), [packEvidence]);
  const populationFindings = useMemo(() => findingEvidence(packEvidence), [packEvidence]);
  const roles = useMemo(() => {
    const set = new Set<string>();
    for (const tier of populationTiers) set.add(tier.role);
    return [...set].sort();
  }, [populationTiers]);

  const activeRole =
    activeRoleState ?? (roles.includes("MIDDLE") ? "MIDDLE" : (roles[0] ?? null));
  const trajectoryFilters = {
    role: activeRole ?? undefined,
    champion: selectedChampion ?? undefined,
  };
  const trajectoryEnabled = Boolean(packV2 && activeRole && selectedChampion);
  const trajectories = useTrajectories(trajectoryFilters, { enabled: trajectoryEnabled });
  const aggregates = usePatchAggregates(trajectoryFilters, { enabled: trajectoryEnabled });

  const headerEntry = useMemo(
    () =>
      populationTiers.find(
        (tier) => tier.role === activeRole && tier.champion === selectedChampion,
      ) ?? null,
    [populationTiers, activeRole, selectedChampion],
  );

  const tierRows = useMemo(
    () => populationTiers.filter((tier) => tier.role === activeRole),
    [populationTiers, activeRole],
  );

  const matchups = useMemo(
    () => matchupEvidence(packEvidence, activeRole, selectedChampion),
    [packEvidence, activeRole, selectedChampion],
  );

  const compFindings = useMemo(
    () =>
      populationFindings.filter(
        (finding) => COMP_RE.test(finding.key) || COMP_RE.test(finding.title),
      ),
    [populationFindings],
  );
  const damageFit = useMemo(
    () => populationFindings.find((finding) => DAMAGE_FIT_RE.test(finding.key)) ?? null,
    [populationFindings],
  );
  const goldWaste = useMemo(
    () => populationFindings.find((finding) => GOLD_WASTE_RE.test(finding.key)) ?? null,
    [populationFindings],
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
      {packEvidence && activeRole && (
        <div
          style={{
            minHeight: 0,
            display: "grid",
            gridTemplateColumns: "minmax(0, 380px) minmax(0, 1fr) minmax(0, 360px)",
            gap: 14,
            alignItems: "start",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
            {headerEntry && <ChampionHeader entry={headerEntry} />}
            <MatchupsCard champion={selectedChampion} matchups={matchups} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
            {compFindings.length > 0 && <CompCard findings={compFindings} />}
            {damageFit && <DamageFitCard finding={damageFit} />}
            <RoleTierList
              role={activeRole}
              rows={tierRows}
              selectedChampion={selectedChampion}
              onSelect={setSelectedChampion}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>
            <BuildOrderCard pack={packV2} />
            <RouteArchetypesCard pack={packV2} />
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

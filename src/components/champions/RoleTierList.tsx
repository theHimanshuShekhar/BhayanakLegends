import type { CSSProperties } from "react";
import type { TierEntry } from "../../api/types";
import { formatRate } from "../format";
import { SectionHead } from "../ui";

// Tier rank is Findings Pack population evidence: blue, not teal.
const TIER_PILL: Record<TierEntry["tier"], CSSProperties> = {
  S: { background: "var(--color-info-low)", color: "var(--color-info)" },
  A: { background: "var(--color-info-low)", color: "var(--color-info)" },
  B: { background: "var(--color-amber-low)", color: "var(--color-amber)" },
  C: { background: "var(--color-surface-3)", color: "var(--color-dim)" },
};

const TIER_ORDER: Record<TierEntry["tier"], number> = { S: 0, A: 1, B: 2, C: 3 };

export function sortTierRows(rows: TierEntry[]): TierEntry[] {
  return [...rows].sort(
    (a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier] || b.win_rate - a.win_rate,
  );
}

export function RoleTierList({
  role,
  rows,
  trapPicks,
  selectedChampion,
  onSelect,
}: {
  role: string;
  rows: TierEntry[];
  trapPicks: Set<string>;
  selectedChampion: string | null;
  onSelect: (champion: string) => void;
}) {
  return (
    <div
      className="card3"
      style={{
        padding: 13,
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <SectionHead label={`ROLE TIER LIST · ${role}`} color="var(--color-dimmer)" />
      <div data-testid="tier-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {rows.map((t) => {
          const selected = t.champion === selectedChampion;
          return (
            <button
              key={`${t.champion}-${t.role}`}
              type="button"
              data-testid={`tier-row-${t.champion}`}
              aria-pressed={selected}
              aria-label={`${t.champion}, ${t.tier} tier, ${role}`}
              onClick={() => onSelect(t.champion)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(t.champion);
                }
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                width: "100%",
                border: 0,
                borderRadius: 5,
                textAlign: "left",
                cursor: "pointer",
                color: "inherit",
                background: selected ? "var(--color-surface-3)" : "transparent",
              }}
            >
              <span
                className="pill"
                style={{ ...TIER_PILL[t.tier], width: 20, justifyContent: "center", padding: "3px 0", fontSize: 10 }}
              >
                {t.tier}
              </span>
              <span style={{ flex: 1, fontSize: 10.5 }}>{t.champion}</span>
              {/* Findings Pack population win rate: blue. */}
              <span className="mono-n" style={{ fontSize: 9.5, color: "var(--color-info)" }}>
                {formatRate(t.win_rate)}
                {trapPicks.has(t.champion) && (
                  <span style={{ color: "var(--color-dimmer)" }}> · trap</span>
                )}
              </span>
            </button>
          );
        })}
        {rows.length === 0 && (
          <div style={{ fontSize: 9.5, color: "var(--color-dimmer)" }}>
            no ≥100-game champions for this role in the pack
          </div>
        )}
      </div>
      <p style={{ margin: 0, fontSize: 9, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
        Tier from pick/ban + win rate among ≥100-game champions this patch.
      </p>
    </div>
  );
}

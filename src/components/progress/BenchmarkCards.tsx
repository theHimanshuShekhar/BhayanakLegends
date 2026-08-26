import type { RoleBenchmark } from "../../api/types";
import { formatCount } from "../format";

function deltaLabel(delta: number): string {
  return delta >= 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1);
}

const METRICS = [
  { key: "cs10", populationKey: "cs10_median", label: "CS@10" },
  { key: "level10", populationKey: "level10_median", label: "LEVEL@10" },
  { key: "gold_diff_10", populationKey: "gold_diff_10_median", label: "GOLD DIFF@10" },
] as const;

export function BenchmarkCards({ rows }: { rows: RoleBenchmark[] }) {
  return (
    <ul
      aria-label="Benchmarks by role"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        gap: 12,
        listStyle: "none",
        margin: 0,
        padding: 0,
      }}
      data-testid="benchmark-cards"
    >
      {rows.flatMap((r) =>
        METRICS.map((metric) => {
          const personal = r.personal[metric.key] ?? null;
          const median = r.population[metric.populationKey] ?? null;
          if (personal == null || median == null) return null;
          const delta = personal - median;
          const good = delta >= 0;
          const scale = Math.max(Math.abs(personal), Math.abs(median));
          const fill =
            scale > 0 ? `${Math.round((Math.abs(personal) / scale) * 1000) / 10}%` : "0%";
          const tick =
            scale > 0 ? `${Math.round((Math.abs(median) / scale) * 1000) / 10}%` : null;
          return (
            <li key={`${r.role}-${metric.key}`} aria-label={`${metric.label} ${r.role}`}>
              <div
                className="card3"
                style={{ padding: 11 }}
                data-testid={`benchmark-${r.role}`}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontSize: 9, letterSpacing: ".08em", color: "var(--color-dimmer)" }}>
                    {metric.label} · {r.role}
                  </span>
                  {/* Outcome framing lives on the pill; the values themselves keep
                      their data-world colors (personal teal, population blue). */}
                  <span
                    className="pill"
                    style={{
                      background: good ? "var(--color-teal-low)" : "var(--color-danger-low)",
                      color: good ? "var(--color-teal)" : "var(--color-soft-rose)",
                      padding: "2px 7px",
                    }}
                  >
                    {deltaLabel(delta)}
                  </span>
                </div>
                {/* Personal History value: teal regardless of favorable/unfavorable. */}
                <div
                  className="mono-n"
                  style={{
                    font: "700 25px/1.1 var(--font-mono)",
                    marginTop: 6,
                    color: "var(--color-teal)",
                  }}
                >
                  {personal.toFixed(1)}
                </div>
                <div
                  data-testid={`benchmark-bar-${r.role}`}
                  style={{
                    position: "relative",
                    marginTop: 8,
                    height: 6,
                    borderRadius: 999,
                    background: "var(--color-deep)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: fill,
                      background: "var(--color-teal)",
                      borderRadius: 999,
                    }}
                  />
                  {tick != null && (
                    <span
                      title={`population median ${median}`}
                      style={{
                        position: "absolute",
                        top: -2,
                        bottom: -2,
                        left: tick,
                        width: 2,
                        background: "var(--color-info)",
                      }}
                    />
                  )}
                </div>
                <div
                  data-testid={`benchmark-pop-${r.role}`}
                  style={{ marginTop: 6, fontSize: 9, color: "var(--color-dimmer)" }}
                >
                  pop median{" "}
                  <span style={{ color: "var(--color-info)" }}>{median}</span> ·{" "}
                  {formatCount(r.population.sample, "games")}
                </div>
              </div>
            </li>
          );
        }),
      )}
    </ul>
  );
}

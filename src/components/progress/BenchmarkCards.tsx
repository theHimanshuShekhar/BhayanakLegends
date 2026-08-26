import type { RoleBenchmark } from "../../api/types";

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
                  <span
                    className="pill"
                    style={{
                      background: good ? "var(--color-teal-low)" : "var(--color-danger-low)",
                      color: good ? "var(--color-teal)" : "#f4c3ce",
                      padding: "2px 7px",
                    }}
                  >
                    {deltaLabel(delta)}
                  </span>
                </div>
                <div
                  className="mono-n"
                  style={{
                    font: "700 25px/1.1 var(--font-mono)",
                    marginTop: 6,
                    color: good ? undefined : "var(--color-danger)",
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
                      background: good ? "var(--color-teal)" : "var(--color-danger)",
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
                        background: "#e9e9ed",
                      }}
                    />
                  )}
                </div>
                <div style={{ marginTop: 6, fontSize: 9, color: "var(--color-dimmer)" }}>
                  pop median {median} · {Math.round(r.population.sample / 1000)}k games
                </div>
              </div>
            </li>
          );
        }),
      )}
    </ul>
  );
}

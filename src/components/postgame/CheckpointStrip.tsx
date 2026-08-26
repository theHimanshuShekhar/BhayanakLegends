import type { PostGameDigest } from "../../api/types";
import { formatGold } from "../format";
import { SectionHead, Unavailable } from "../ui";


/**
 * Checkpoint strip: signed gold deltas at 10/15/20, green when ahead, red
 * when behind. Diagnostic — describes what happened, never instructs.
 */
export function CheckpointStrip({ digest }: { digest: PostGameDigest | null }) {
  const c = digest?.checkpoints;
  const cells = [
    { key: "10", label: "GOLD @10", value: c?.gold_diff_10 },
    { key: "15", label: "GOLD @15", value: c?.gold_diff_15 },
    { key: "20", label: "GOLD @20", value: c?.gold_diff_20 },
  ];
  return (
    <section
      className="card3b"
      data-testid="checkpoint-strip"
      aria-labelledby="postgame-checkpoints-heading"
      style={{ flex: "none", marginTop: 12, padding: 14 }}
    >
      <SectionHead
        color="var(--color-soft-blue)"
        label={
          <>
            <span id="postgame-checkpoints-heading">Checkpoints</span>
            <span
              data-testid="checkpoint-source"
              style={{ font: "400 8.5px var(--font-mono)", letterSpacing: ".08em", color: "var(--color-dimmer)", textTransform: "none" }}
            >
              Diagnostic · Personal History
            </span>
          </>
        }
      />
      <SectionHead level={3} dot={false} label="Gold difference checkpoints" />
      <ul
        aria-label="Gold difference checkpoints"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: 8,
          listStyle: "none",
          margin: 0,
          padding: 0,
        }}
      >
        {cells.map((cell) => (
          <li
            key={cell.key}
            data-testid={`checkpoint-${cell.key}`}
            style={{
              minWidth: 0,
              padding: "8px 9px",
              borderRadius: 12,
              background: "var(--color-surface-2)",
              boxShadow: "var(--shadow-z1)",
            }}
          >
            <div style={{ fontSize: 8, letterSpacing: ".08em", color: "var(--color-dimmer)" }}>{cell.label}</div>
            <div
              className="mono-n"
              style={{
                font: "700 14px var(--font-mono)",
                color: cell.value == null ? "var(--color-dimmer)" : "var(--color-teal)",
              }}
            >
              {cell.value == null ? <Unavailable reason="gold checkpoint not reported" /> : formatGold(Math.round(cell.value))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

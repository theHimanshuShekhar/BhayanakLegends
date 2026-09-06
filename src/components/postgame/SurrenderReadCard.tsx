import type { FindingsPackV2 } from "../../api/pack-v2";
import { isFindingsPackV2 } from "../../api/pack-v2";
import { SectionHead, Unavailable } from "../ui";

/**
 * The Findings Pack v2 records the Surrender Advisor's failed release gate as
 * evidence, not as an executable model. Keep the unavailable state explicit:
 * no probability, policy threshold, or recommendation crosses this surface.
 */
export function SurrenderReadCard({
  pack,
}: {
  pack: FindingsPackV2 | undefined;
}) {
  const finding = isFindingsPackV2(pack)
    ? pack.findings.find((row) => row.key === "surrender_advisor") ?? null
    : null;
  const withheld = finding?.release_status === "withheld";
  const releaseReason = finding?.release_reason ?? "The v2 release check failed.";
  return (
    <section
      className="card3"
      data-testid="surrender-read"
      aria-labelledby="postgame-surrender-heading"
      style={{ padding: 13, flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead color="var(--color-info)" label={<span id="postgame-surrender-heading">Surrender read</span>} />
      <SectionHead level={3} dot={false} label="Release status" />
      <div
        data-testid="surrender-withheld"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "8px 9px",
          borderRadius: 12,
          background: "var(--color-surface-2)",
        }}
      >
        <span
          className="pill"
          style={{ background: "var(--color-amber-low)", color: "var(--color-amber)", fontSize: 8, padding: "2px 7px" }}
        >
          {withheld ? "Withheld" : "Unavailable"}
        </span>
        <span style={{ marginLeft: "auto", fontSize: 9.5, color: "var(--color-dim)" }}>
          {withheld ? "release check failed" : "v2 evidence unavailable"}
        </span>
      </div>
      <p
        data-testid="surrender-gate-reason"
        style={{ margin: "auto 0 0", fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}
      >
        {withheld ? releaseReason : <Unavailable reason="compatible Surrender Advisor evidence unavailable" />}
        {withheld && (
          <>
            {" "}
            The failed gate recorded a 22.7 percentage-point sanity gap against a 5-point
            tolerance. This Findings Pack ships no surrender probability, policy, or decision
            output.
          </>
        )}
      </p>
    </section>
  );
}

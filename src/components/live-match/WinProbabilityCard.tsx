import type { FindingsPackV2 } from "../../api/pack-v2";
import type { InGameSnapshot, LiveEventDelta } from "../../api/types";
import { formatClock, formatPercentagePoints, formatRate, formatUnavailable } from "../format";
import { SectionHead } from "../ui";

function eventDeltaLabel(delta: LiveEventDelta): string {
  const value =
    delta.suppression_status === "available" && delta.delta_probability != null
      ? formatPercentagePoints(delta.delta_probability * 100)
      : formatUnavailable(delta.reason ?? "event delta unavailable");
  const provenance =
    delta.suppression_status === "available"
      ? ` · ${formatClock(delta.pre_observed_game_time_s ?? delta.t_s)}→${formatClock(delta.post_observed_game_time_s ?? delta.t_s)}`
      : "";
  return `${delta.name} @${formatClock(delta.t_s)} · ${value}${provenance}`;
}

function hasLiveProvenance(
  result: InGameSnapshot["inference"] | LiveEventDelta,
  modelVersion: string,
  packVersion: string,
): boolean {
  return result.model_version === modelVersion && result.pack_version === packVersion;
}

export function WinProbabilityCard({
  pack,
  clockS,
  active,
  packVersion,
  inference,
  eventDeltas = [],
}: {
  pack: FindingsPackV2 | undefined;
  clockS: number;
  active: boolean;
  packVersion: string | null;
  inference?: InGameSnapshot["inference"];
  eventDeltas?: LiveEventDelta[];
}) {
  const packV2 = pack;
  const declaration = packV2?.models?.live_wp;
  const activeModelVersion = declaration?.model_card?.model_version;
  const activePackVersion = packV2?.pack_version;
  const modelContractReady =
    packV2?.feature_contracts.models?.live_wp === "live-wp-v2" &&
    declaration?.model_id === "live-wp-v2" &&
    declaration.release_status === "available" &&
    declaration.artifact != null &&
    declaration.model_card?.model_id === "live-wp-v2" &&
    declaration.model_card.feature_contract_version === "live-wp-v2" &&
    activeModelVersion != null &&
    activePackVersion != null &&
    packVersion === activePackVersion;
  const visibleEventDeltas = modelContractReady && activeModelVersion != null && activePackVersion != null
    ? eventDeltas.map((delta) =>
        delta.suppression_status === "available" &&
        !hasLiveProvenance(delta, activeModelVersion, activePackVersion)
          ? {
              ...delta,
              suppression_status: "suppressed" as const,
              baseline_probability: null,
              event_probability: null,
              delta_probability: null,
              reason: "event delta provenance differs from active model",
            }
          : delta,
      )
    : [];
  const liveInference = active && modelContractReady ? inference : undefined;
  const inferenceProvenanceReady =
    liveInference != null &&
    activeModelVersion != null &&
    activePackVersion != null &&
    hasLiveProvenance(liveInference, activeModelVersion, activePackVersion);
  const available =
    inferenceProvenanceReady &&
    liveInference.status === "available" &&
    liveInference.probability != null;
  const provenanceMismatch = liveInference?.status === "available" && !inferenceProvenanceReady;
  const value = available
    ? formatRate(liveInference.probability)
    : formatUnavailable(
        provenanceMismatch
          ? "live result provenance differs from active model"
          : modelContractReady
            ? liveInference?.reason ?? "compatible live inputs unavailable"
            : "live model contract unavailable",
      );
  const statusLabel = !modelContractReady
    ? "unavailable"
    : provenanceMismatch
      ? "incompatible"
      : liveInference?.status ?? "unavailable";
  const versionLabel = available && liveInference.model_version
    ? ` · model ${liveInference.model_version}`
    : "";
  return (
    <section
      className="card3b"
      data-testid="wp-band"
      aria-labelledby="wp-band-heading"
      style={{ padding: 14, display: "flex", flexDirection: "column" }}
    >
      <SectionHead
        color="var(--color-info)"
        label={
          <span id="wp-band-heading">
            {`WIN PROBABILITY · LIVE MODEL${packVersion ? ` ${packVersion}` : ""}`}
          </span>
        }
        right={
          <span
            className="mono-n"
            data-testid="wp-value"
            style={{ font: "700 20px var(--font-mono)", color: available ? "var(--color-info)" : "var(--color-dimmer)" }}
          >
            {value}
          </span>
        }
      />
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 5 }}>
        <span
          className="pill"
          data-testid="wp-status"
          style={{
            background: available ? "var(--color-info-low)" : "var(--color-surface-3)",
            color: available ? "var(--color-info)" : "var(--color-dim)",
            fontSize: 8,
            padding: "2px 7px",
          }}
        >
          {statusLabel}
        </span>
      </div>
      <svg
        viewBox="0 0 640 108"
        style={{ width: "100%", height: 100, marginTop: 6 }}
        preserveAspectRatio="none"
        aria-label={available ? "Live model probability" : "Live model probability unavailable"}
      >
        <line x1="0" y1="54" x2="640" y2="54" stroke="rgba(233,233,237,.16)" strokeWidth="1" />
        <line
          x1="0"
          y1="54"
          x2="640"
          y2="54"
          stroke="rgba(233,233,237,.28)"
          strokeWidth="2"
          strokeDasharray="4 5"
          strokeLinecap="round"
        />
      </svg>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 8,
          fontSize: 9,
          color: "var(--color-dimmer)",
          marginTop: 1,
        }}
      >
        <span className="mono-n">0:00</span>
        <span>{available ? `observed ${formatClock(liveInference?.observed_game_time_s ?? clockS)}` : statusLabel}</span>
        <span className="mono-n">{formatClock(clockS)}</span>
      </div>
      {visibleEventDeltas.length > 0 && (
        <div data-testid="wp-event-deltas" style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 8 }}>
          {visibleEventDeltas.map((delta) => (
            <div key={delta.event_id} style={{ fontSize: 9.5, color: "var(--color-dim)" }}>
              {eventDeltaLabel(delta)}
            </div>
          ))}
        </div>
      )}
      <p style={{ margin: "8px 0 0", fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
        {available
          ? `Exact live feature contract${versionLabel}; event deltas use the same model pair. Personal History remains separate from live inference.`
          : `Live inference is ${statusLabel}; no probability is shown without an exact model input contract. Personal History remains separate from live inference.`}
      </p>
    </section>
  );
}

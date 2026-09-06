import { useMemo, useState } from "react";
import type { PostGameDigest } from "../../api/types";
import type { FindingsPackV2 } from "../../api/pack-v2";
import { useWhatIf } from "../../api/hooks";
import { isFindingsPackV2 } from "../../api/pack-v2";
import { formatRate } from "../format";
import { SectionHead } from "../ui";

interface WhatIfPanelProps {
  pack?: FindingsPackV2;
  digest?: PostGameDigest | null;
}
function featureValues(value: unknown): Record<string, number | null> | null {
  if (value == null || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, number | null>;
}

export function WhatIfPanel({ pack, digest = null }: WhatIfPanelProps) {
  const whatIf = useWhatIf();
  const [adjustments, setAdjustments] = useState<Record<string, number>>({});
  const packV2 = isFindingsPackV2(pack) ? pack : null;
  const modelContractReady =
    packV2?.feature_contracts.models?.personal_what_if === "loltrends-cutoff-v2";
  const declaration = packV2?.models?.personal_what_if;
  const modelCard =
    declaration?.release_status === "available" ? declaration.model_card : null;
  const controls = useMemo(
    () =>
      (modelCard?.features ?? []).filter(
        (feature) =>
          feature.adjustable &&
          Number.isFinite(feature.bounds.min) &&
          Number.isFinite(feature.bounds.max) &&
          feature.bounds.min <= feature.bounds.max,
      ),
    [modelCard],
  );
  const baselineFeatures = featureValues(digest?.features);
  const baselineReady =
    modelContractReady &&
    digest?.feature_contract_version === "loltrends-parity-v2" &&
    digest.personal_history_eligibility === "eligible" &&
    baselineFeatures !== null &&
    modelCard !== null &&
    modelCard.features.every((feature) => {
      const value = baselineFeatures[feature.name];
      return typeof value === "number" && Number.isFinite(value);
    });
  const unavailableReason =
    !packV2
      ? "Findings Pack v2 is unavailable."
      : !declaration
        ? "Personal What-If model declaration is unavailable."
        : declaration.release_status !== "available"
          ? declaration.release_reason ?? "Personal What-If model is unavailable."
          : !modelCard
            ? "Personal What-If model card is unavailable."
            : !modelContractReady
              ? "Personal What-If model contract is unavailable."
              : !baselineReady
                ? "Personal History baseline is unavailable or does not match the model contract."
                : controls.length === 0
                  ? "No adjustable features are declared by the model card."
                  : null;
  const canRun = unavailableReason === null && !whatIf.isPending;
  const response = whatIf.data;
  const prediction =
    response?.status === "available" && response.probability != null
      ? formatRate(response.probability)
      : "Unavailable";
  const responseReason =
    response && response.status !== "available"
      ? response.reason ?? `What-If status: ${response.status}.`
      : null;

  return (
    <div
      className="card3b"
      data-testid="what-if-panel"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead
        level={3}
        label={`WHAT-IF SIMULATOR · ${unavailableReason ? "UNAVAILABLE" : "LOCAL MODEL"}`}
        color="var(--color-info)"
      />
      {controls.length > 0 ? (
        controls.map((feature) => {
          const baseline =
            baselineFeatures !== null &&
            typeof baselineFeatures[feature.name] === "number" &&
            Number.isFinite(baselineFeatures[feature.name])
              ? baselineFeatures[feature.name]
              : null;
          const value = adjustments[feature.name] ?? baseline;
          return (
            <label key={feature.name} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5 }}>
                <span style={{ color: "var(--color-dim)" }}>{feature.name}</span>
                <span className="mono-n" style={{ color: "var(--color-dimmer)" }}>
                  {value == null ? "Unavailable" : value.toFixed(2)}
                </span>
              </span>
              <input
                type="range"
                min={feature.bounds.min}
                max={feature.bounds.max}
                step="any"
                value={value ?? feature.bounds.min}
                disabled={!canRun || value == null}
                aria-label={`${feature.name}${value == null ? " unavailable" : ""}`}
                data-testid={`what-if-control-${feature.name}`}
                onChange={(event) =>
                  setAdjustments((current) => ({
                    ...current,
                    [feature.name]: Number(event.target.value),
                  }))
                }
              />
            </label>
          );
        })
      ) : (
        <div data-testid="what-if-no-controls" role="status" style={{ fontSize: 9.5, color: "var(--color-dimmer)" }}>
          No model-declared adjustable features are available.
        </div>
      )}
      <button
        type="button"
        disabled={!canRun}
        data-testid="what-if-run"
        onClick={() => whatIf.mutate(adjustments)}
        style={{
          alignSelf: "flex-start",
          border: "1px solid var(--color-line)",
          borderRadius: 999,
          background: canRun ? "var(--color-info-low)" : "var(--color-surface-2)",
          color: canRun ? "var(--color-info)" : "var(--color-dimmer)",
          padding: "5px 10px",
          cursor: canRun ? "pointer" : "default",
        }}
      >
        {whatIf.isPending ? "Evaluating…" : "Evaluate local model"}
      </button>
      <div
        style={{
          marginTop: "auto",
          padding: "9px 10px",
          borderRadius: 12,
          background: "var(--color-accent-low)",
          boxShadow: "var(--shadow-z1)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 9.5, color: "var(--color-chip-text)" }}>Predicted win rate</span>
          <span
            className="mono-n"
            data-testid="what-if-prediction"
            style={{ font: "700 16px var(--font-mono)", color: "var(--color-chip-text)" }}
          >
            {prediction}
          </span>
        </div>
      </div>
      <p
        style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        data-testid="what-if-caption"
      >
        {unavailableReason
          ? `Personal what-if estimates are unavailable because ${unavailableReason.toLowerCase()}`
          : responseReason ?? "Local ONNX model; this result is scoped to the declared Personal History feature contract."}
      </p>
    </div>
  );
}

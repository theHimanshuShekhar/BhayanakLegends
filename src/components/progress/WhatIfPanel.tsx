import { useEffect, useMemo, useState } from "react";
import type { PostGameDigest } from "../../api/types";
import type { FindingsPackV2 } from "../../api/pack-v2";
import { useOwnerContext, useWhatIf } from "../../api/hooks";
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
const CONTROL_LABELS: Record<string, string> = {
  unseen_recall_share_by_20m: "Safe-recall share through 20 minutes",
  avg_banked_gold_at_recall_by_20m: "Gold carried into recalls through 20 minutes",
};

export function WhatIfPanel({ pack, digest = null }: WhatIfPanelProps) {
  const owner = useOwnerContext();
  const whatIf = useWhatIf();
  const [adjustments, setAdjustments] = useState<Record<string, number>>({});
  const [submittedSnapshot, setSubmittedSnapshot] = useState<string | null>(null);
  const packV2 = isFindingsPackV2(pack) ? pack : null;
  const modelContractReady =
    packV2?.feature_contracts.models?.personal_what_if === "loltrends-cutoff-v2";
  const declaration = packV2?.models?.personal_what_if;
  const modelCard =
    declaration?.release_status === "available" ? declaration.model_card : null;
  const cardControls = useMemo(
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
  const controls = useMemo(
    () => cardControls.filter((feature) => Object.prototype.hasOwnProperty.call(CONTROL_LABELS, feature.name)),
    [cardControls],
  );
  const baselineFeatures = featureValues(digest?.features);
  const plateBaseline = baselineFeatures?.plates_taken_by_14m;
  const plateModelInput =
    modelCard?.features.some((feature) => feature.name === "plates_taken_by_14m") === true;
  const plateEvidence = packV2?.habits.find(
    (habit) =>
      habit.feature === "plates_taken_by_14m" &&
      habit.release_status === "available" &&
      habit.tier === "a-lite" &&
      habit.review_context_only === true,
  );
  const baselineValuesMatch =
    modelCard !== null &&
    baselineFeatures !== null &&
    cardControls.length > 0 &&
    modelCard.features.every((feature) => {
      const value = baselineFeatures[feature.name];
      return (
        typeof value === "number" &&
        Number.isFinite(value) &&
        value >= feature.bounds.min &&
        value <= feature.bounds.max
      );
    });
  const baselineReady =
    modelContractReady &&
    digest?.feature_contract_version === "loltrends-parity-v2" &&
    digest.personal_history_eligibility === "eligible" &&
    baselineValuesMatch;
  const submittedAdjustments = useMemo(
    () =>
      Object.fromEntries(
        controls.flatMap((feature) => {
          const value = adjustments[feature.name] ?? baselineFeatures?.[feature.name];
          return typeof value === "number" && Number.isFinite(value)
            ? [[feature.name, value]]
            : [];
        }),
      ),
    [adjustments, baselineFeatures, controls],
  );
  const inputSnapshot = JSON.stringify({
    owner: owner.ownerKey,
    generation: owner.generation,
    match: digest?.match_id ?? null,
    pack: packV2?.pack_version ?? null,
    model: modelCard?.model_version ?? null,
    baseline: baselineFeatures,
    adjustments: submittedAdjustments,
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
                ? "Personal History does not provide a complete finite baseline inside the model-card domains."
                : cardControls.length === 0
                  ? "No adjustable features are declared by the model card."
                  : controls.length === 0
                    ? "No safe model-card-adjustable controls are available."
                    : null;

  useEffect(() => {
    setAdjustments({});
    setSubmittedSnapshot(null);
  }, [
    owner.ownerKey,
    owner.generation,
    digest?.match_id,
    digest?.feature_contract_version,
    digest?.personal_history_eligibility,
    packV2?.pack_version,
    modelCard?.model_version,
  ]);

  const canRun = unavailableReason === null && !whatIf.isPending;
  const response = whatIf.data;
  const availableResponse =
    unavailableReason === null &&
    submittedSnapshot === inputSnapshot &&
    response?.status === "available" &&
    typeof response.probability === "number" &&
    Number.isFinite(response.probability) &&
    typeof response.baseline_probability === "number" &&
    Number.isFinite(response.baseline_probability) &&
    response.model_version === modelCard?.model_version &&
    response.pack_version === packV2?.pack_version
      ? response
      : null;
  const responseAvailable = availableResponse !== null;
  const currentProbability = availableResponse
    ? formatRate(availableResponse.baseline_probability)
    : "Unavailable";
  const simulatedProbability = availableResponse
    ? formatRate(availableResponse.probability)
    : "Unavailable";
  const responseReason =
    response && response.status !== "available"
      ? response.reason ?? `What-If status: ${response.status}.`
      : whatIf.error
        ? "Local model request failed."
        : response && !responseAvailable
          ? "Model provenance is unavailable or stale."
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
      {modelCard && packV2 ? (
        <div
          data-testid="what-if-model-scope"
          style={{ fontSize: 9, lineHeight: 1.4, color: "var(--color-dim)" }}
        >
          Model {modelCard.model_version} · Pack {packV2.pack_version} · supported patches{" "}
          {modelCard.patch_scope.min}–{modelCard.patch_scope.max}
        </div>
      ) : null}
      {baselineFeatures !== null ? (
        <div
          data-testid="what-if-plate-baseline"
          style={{ fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dim)" }}
        >
          <span>Personal History plate value: </span>
          <span className="mono-n">
            {typeof plateBaseline === "number" && Number.isFinite(plateBaseline)
              ? `${plateBaseline} plates`
              : "Unavailable"}
          </span>
          <div style={{ color: "var(--color-dimmer)" }}>
            {plateModelInput
              ? "Read-only input to this model; this app does not offer plate adjustments."
              : declaration?.release_status === "available" && modelCard !== null
                ? "Not used as an input by this model."
                : "Not used by a What-If model while its model card is unavailable."}
          </div>
        </div>
      ) : null}
      {packV2 ? (
        <div
          data-testid="what-if-plate-evidence"
          style={{ fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        >
          {plateEvidence ? (
            <>
              Population evidence: a-lite; weak, era-sensitive review context only.
              {plateEvidence.caveats.length > 0 ? ` ${plateEvidence.caveats.join(" ")}` : ""}
            </>
          ) : (
            "Population evidence for plates is unavailable; no population comparison is shown."
          )}
        </div>
      ) : null}


      {controls.length > 0 ? (
        controls.map((feature) => {
          const baseline =
            baselineFeatures !== null &&
            typeof baselineFeatures[feature.name] === "number" &&
            Number.isFinite(baselineFeatures[feature.name])
              ? baselineFeatures[feature.name]
              : null;
          const value = adjustments[feature.name] ?? baseline;
          const outOfDomainBaseline =
            baseline !== null &&
            (baseline < feature.bounds.min || baseline > feature.bounds.max);
          return (
            <label key={feature.name} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5 }}>
                <span style={{ color: "var(--color-dim)" }}>
                  {CONTROL_LABELS[feature.name] ?? feature.name.replace(/_/g, " ")}
                </span>
                <span className="mono-n" style={{ color: "var(--color-dimmer)" }}>
                  {value == null ? "Unavailable" : `${value} ${feature.unit}`}
                </span>
              </span>
              {baseline === null ? (
                <div role="status" style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
                  No compatible Personal History value is available.
                </div>
              ) : outOfDomainBaseline ? (
                <div role="status" style={{ fontSize: 9, color: "var(--color-amber)" }}>
                  This Personal History value is outside the declared model domain.
                </div>
              ) : (
                <input
                  type="range"
                  min={feature.bounds.min}
                  max={feature.bounds.max}
                  step="any"
                  value={value ?? feature.bounds.min}
                  disabled={!canRun || value == null}
                  aria-label={`${CONTROL_LABELS[feature.name] ?? feature.name.replace(/_/g, " ")} (${feature.unit})${value == null ? " unavailable" : ""}`}
                  data-testid={`what-if-control-${feature.name}`}
                  onChange={(event) =>
                    setAdjustments((current) => ({
                      ...current,
                      [feature.name]: Number(event.target.value),
                    }))
                  }
                />
              )}
            </label>
          );
        })
      ) : (
        <div data-testid="what-if-no-controls" role="status" style={{ fontSize: 9.5, color: "var(--color-dimmer)" }}>
          No safe model-card-adjustable controls are available.
        </div>
      )}
      <button
        type="button"
        disabled={!canRun}
        data-testid="what-if-run"
        onClick={() => {
          setSubmittedSnapshot(inputSnapshot);
          whatIf.mutate(submittedAdjustments);
        }}
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
          <span style={{ fontSize: 9.5, color: "var(--color-chip-text)" }}>Current probability</span>
          <span className="mono-n" data-testid="what-if-current" style={{ font: "700 16px var(--font-mono)", color: "var(--color-chip-text)" }}>
            {currentProbability}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 4 }}>
          <span style={{ fontSize: 9.5, color: "var(--color-chip-text)" }}>Simulated probability</span>
          <span
            className="mono-n"
            data-testid="what-if-prediction"
            style={{ font: "700 16px var(--font-mono)", color: "var(--color-chip-text)" }}
          >
            {simulatedProbability}
          </span>
        </div>
        {availableResponse ? (
          <div
            data-testid="what-if-provenance"
            style={{ marginTop: 4, fontSize: 8.5, color: "var(--color-chip-text)" }}
          >
            Model {availableResponse.model_version} · Pack {availableResponse.pack_version}
          </div>
        ) : null}
      </div>
      <p
        style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        data-testid="what-if-caption"
      >
        {availableResponse && modelCard ? (
          <>
            {modelCard.caveats.map((caveat) => (
              <span key={caveat}>{caveat} </span>
            ))}
            Association only; not causal.
          </>
        ) : (
          <>
            {unavailableReason
              ? `Personal what-if estimates are unavailable because ${unavailableReason.toLowerCase()}`
              : responseReason ?? "Local ONNX model; this result is scoped to the declared Personal History feature contract."}{" "}
            Association only; not causal.
          </>
        )}
      </p>
    </div>
  );
}

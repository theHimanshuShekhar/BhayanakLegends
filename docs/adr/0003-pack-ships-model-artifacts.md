# The Findings Pack ships model artifacts, not just numbers

The live Companion screen needs P(win) inference on real-time game state (win-probability gauge, surrender advisor at the 15-minute vote), and the Improvement Journal's what-if simulator needs the same predictor seeded from personal history. Static pack thresholds cannot power these honestly, so the pack schema extends beyond ADR-0004's "effect sizes, thresholds, caveats": it also carries versioned model artifacts — the Honest Model (pre-~20-min predictor) and the Surrender Advisor — plus their feature contract, so the sidecar can map Live Client Data state onto loltrends' leakage-discipline allowlist and infer locally.

## Consequences

- Pack versioning must now cover model binaries (artifact format + feature-contract compatibility), not just JSON findings.
- Inference runs offline on the user's machine; no match data leaves it.

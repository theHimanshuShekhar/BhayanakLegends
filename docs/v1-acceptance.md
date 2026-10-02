# Web-view v1 acceptance

Status: complete for the agreed web-view scope. Implementation and tests were delegated to GPT-6.1 Sol in an isolated worktree; the orchestrator reviewed the changes and both viewport renders, with all findings resolved before the local merge.

Scope: local browser UI plus FastAPI sidecar, canonical Findings Pack v7, and owner-scoped Personal History. Native packaging, Windows testing, publication, and real Riot/League validation are deferred. Fixture replay validates app behavior, not connectivity to a real client or Riot service.

## Required flows

- Journal onboarding: settings/key save, clear feedback for invalid input and failed requests, saved-key input cleared, account isolation, Backfill start/cancel/error/retry, and no secrets in responses or retained logs.
- Personal review: history summary, role/champion filters, recent result windows, observed feature trajectories, latest post-game checkpoint/observation missing-data states, and true patch counts/win rates.
- Champions: labeled population tiers and declared matchup evidence, selected champion Personal History, loading/empty/error states, and preserved sample/provenance/caveat context.
- Live bridge replay: integer champ-select bans, enemy-name stripping, assigned role and completed-lock evidence, in-game roster/inventory/events, and phase/reconnect/end/new-game transitions. Patch discovery accepts the official JSON string, refreshes at observed lifecycle boundaries, and fails closed with bounded retries.
- All six routes: keyboard/focus, compact layout, 200% zoom, reduced motion, loading/empty/error feedback, and strict browser console/page-error checks. Settled renders are captured at 1280×820 and 980×620.

## Evidence boundaries

Canonical Live WP and Personal What-If remain withheld. Synthetic available-model fixtures prove runtime/interaction mechanics only. Current checkpoint Benchmarks lack compatible population features; syncing cannot fix a missing pack contract. Habit outcomes remain empty without an exact extractor/threshold; personal observations are not habit verdicts. Population associations are not evaluations of the current live game. Unsupported deaths charts, loadouts, and gameplans are omitted.

The latest digest comes from synced Personal History, not automatically from a live game ending. Local data remains scoped to the resolved account; a pending or failed account switch must not expose the previous account's history.

## Validation record

Validated on 2026-10-02 in the Linux browser worktree:

- Backend: 560 passed, 4 skipped; `/tmp/v1-backend-full.log`. Backend source remained unchanged after this gate.
- UI: 215 passed across 26 files after the final visual fixes; `/tmp/v1-ui-final.log`.
- Production build and TypeScript: passed; `/tmp/v1-build-final.log`. Vite retains the existing chunk-size warning.
- Browser coverage: all 50 distinct Chromium tests have passing evidence across runs. The initial full suite recorded 46 passed and 4 failed; those failures were diagnosed and corrected. Final replay plus smoke passed 19/19 (`/tmp/v1-browser-replay-smoke-final.log`). Final design-system checks passed 6/6 and the other nine UI-integrity checks passed (`/tmp/v1-browser-final-visual.log`); the settled six-route screenshot test then passed separately with the final assertions (`/tmp/v1-browser-screenshots-final.log`). Account isolation (6), history feature insights (5), and sync freshness (4) passed in the initial full suite and were unaffected by subsequent visual changes. This is module-level evidence, not a claim of one final 50-test clean run.

Twelve final canonical/official screenshots, at 1280×820 and 980×620, are preserved under `/tmp/v1-browser-accepted-artifacts/ui-integrity-v1-settled-ca-a81be-cial-Live-Companion-renders-chromium/`. Browser checks assert a dark active-game background and all ten champ-select roster cards within the viewport at 980 and 640 pixels; native overlay transparency is restricted to the native shell.

The canonical pack SHA-256 remains `87f67379072f3c1af36274bc116f8b677db9656a61cb52a8cee35183a3a820cd`. No native, Windows, or real-service validation is implied by these results.

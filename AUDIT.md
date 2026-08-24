# Bhayanak Legends Project Audit

## Executive verdict

**Release readiness: blocked.** The architecture is coherent and the current backend suite is green, but the live UI cutover leaves the frontend build and tests red, the real Riot Backfill path is broken, the new LCU bridge misreads the League lockfile, and several user-facing personal metrics are mathematically or semantically wrong.

The strongest parts are the explicit domain vocabulary, frozen frontend/backend contract, local-only Personal History boundary, loopback token authentication, schema-validated Findings Pack, strict TypeScript configuration, and compliance-aware champ-select UI. The highest risks are not style problems; they are end-to-end truth and operability failures at the seams between otherwise well-shaped modules.

### Finding counts

| Severity | Count | Meaning |
|---|---:|---|
| P0 — blocking | 3 | A core task or release gate cannot complete |
| P1 — major | 11 | Incorrect guidance, security gap, contract break, or missing release requirement |
| P2 — moderate | 6 | Reliability, UX, test, or maintainability weakness with a workaround |
| **Total** | **20** | |

### Immediate stop-ship items

1. **The live UI cutover leaves the frontend red.** `pnpm build` fails on `YourSideCard` typing; `pnpm vitest run` has 6 failed tests plus an unhandled `PlayerList` exception.
2. **Riot Backfill cannot fetch its first match.** `_http_fetcher()` is declared `async` but passed to `_process()` without awaiting it; the worker receives a coroutine instead of a callable.
3. **The new LCU lockfile parser uses the PID as the port.** League lockfiles are `process:pid:port:password:protocol`; the parser reads field 2 as the port.

## Audit scope and method

Reviewed:

- Product language and requirements: `CONTEXT.md`, `docs/CONTRACT.md`, all eight ADRs, `README.md`, and repository rules.
- Backend: API construction, auth, models, persistence, Backfill, Riot client, extraction, Findings Pack, data routers, SSE, live detection, the current uncommitted LCU/live work, and tests.
- Frontend: API client and hooks, SSE, all six routes, representative components, design tokens, component tests, and E2E smoke coverage.
- Desktop/release: Tauri process management, capabilities, bundle config, Cargo dependencies, CI, and release workflow.
- Runtime behavior: imported 150 real dev matches into an isolated sidecar, exercised the browser UI, reproduced Backfill/settings failures, measured contrast/overflow/target sizes, and ran the project checks and dependency audits.

The working tree changed during the audit. The final snapshot includes user-owned uncommitted live-bridge work across backend code, contract documentation, fixtures, and tests. This audit does not modify that work.

## Requirements coverage

| Product/architecture requirement | State | Evidence |
|---|---|---|
| Tauri shell spawns a loopback sidecar with an ephemeral token | Partial | Implemented in `src-tauri/src/lib.rs`, but no readiness handshake or restart path |
| REST/SSE access through `src/api/client.ts` and `src/api/sse.ts` | Implemented | No direct frontend fetches found outside the API module |
| Bundled, schema-validated Findings Pack | Implemented | `PackStore`, JSON Schema, and pack tests are present |
| Atomic Findings Pack updates from releases | Missing | ADR-0005 has no updater implementation |
| Model-bearing pack and local inference | Missing/disclosed | UI explicitly says the Honest Model and Surrender Advisor have not shipped |
| Era-first, resumable Riot Backfill | Broken/partial | Folder import works; real Riot flow fails; older-era continuation is not implemented |
| Personal feature definitions stay aligned with LoLTrends | Violated | App-owned extractor implements different proxies despite ADR-0001 |
| Live champ-select and in-game guidance | In-progress/broken | Rich snapshots are wired into routes/components, but the frontend does not compile and its route tests are red |
| Improvement Journal | Partial | Summary/digest render, but habits are always `n/a` and progress metrics are wrong |
| Windows Credential Manager / DPAPI key storage | Missing | Riot key is stored in plaintext SQLite settings |
| Always-on-top champ-select and in-game windows | Missing | One normal 1280×820 window; no always-on-top calls or compact window modes |
| Signed application auto-update | Missing | Release emits updater metadata, but the app has no updater plugin/config/runtime |
| Enemy-name and enemy-timer compliance | Good | Champ-select enemy names have no frontend data path; current WIP drops them in the service layer; enemy timers are absent |

## Detailed findings

### BL-001 — P0 — Live UI cutover leaves frontend build and tests red

**Location:** `src/components/champ-select/YourSideCard.tsx:7-19`, `src/components/live-match/PlayerList.tsx:114-118`, `src/api/hooks.ts:9-21`

The rich snapshot migration reached both routes and several components, but its type/runtime boundaries are incomplete. `YourSideCard` declares `rows` as one cell *or* an array of nulls instead of an array whose elements are cell-or-null. `PlayerList` guards `snapshot` but not `snapshot.teams`, so stale/old fixture shapes throw while rendering. The new hooks also create a second request implementation in `hooks.ts`, contrary to the frozen rule that all API access goes through `client.ts`; it reads `connection()` synchronously and can receive an empty base/token on a cold load.

**Observed:** Latest `pnpm build` exits 2 with four TypeScript errors in `YourSideCard`. Latest `pnpm vitest run` reports **2 failed files, 6 failed tests, 49 passed**, plus an unhandled `TypeError: Cannot read properties of undefined (reading 'order')` in `PlayerList`.

**Impact:** The frontend cannot produce a release bundle. The test runtime can crash on old/coarse snapshot data, so the partial migration is not backward-safe even in the development harness.

**Fix:** Finish the cutover as one boundary:

1. Type `rows` as `((typeof cells)[number] | null)[]`.
2. Normalize idle/missing team shapes before rendering and update every fixture to the rich contract.
3. Put typed `/live/session` and `/live/ingame` methods in `src/api/client.ts`; remove the duplicate hook-local fetcher.
4. Ensure connection resolution completes before EventSource or snapshot requests use the base/token.
5. Add active rich-SSE route tests for player, champion, item, event, and compliance behavior.

**Proof required:** `pnpm build` and all 55 frontend tests pass without unhandled errors; active fixture replay updates both routes without a poll and enemy champ-select names remain absent.

### BL-002 — P0 — Real Riot Backfill passes a coroutine where a fetch function is required

**Location:** `backend/src/bhayanak_legends/sync.py:205`, `backend/src/bhayanak_legends/sync.py:209-218`, `backend/src/bhayanak_legends/sync.py:248-258`

`_http_fetcher()` is an `async def` that returns an async `fetch` closure. `_riot_flow()` calls `self._process(self._http_fetcher(client), ...)` without awaiting the factory. `_process()` then executes `fetch_pair(match_id)` on a coroutine object.

**Observed reproduction:** `TypeError: 'coroutine' object is not callable` at `sync.py:218`, plus `RuntimeWarning: coroutine 'SyncService._http_fetcher' was never awaited`.

**Impact:** Folder import passes while the user-facing Riot Backfill fails on the first queued match. Existing tests exercise import only and therefore miss the release-critical path.

**Fix:** Make `_http_fetcher` a normal `def` returning the async closure, or await the factory before passing it. Prefer the normal factory: it performs no asynchronous work itself. Add a fake-client integration test that starts the real service, resolves a Riot ID, paginates IDs, fetches detail/timeline pairs, persists rows, and reaches a terminal `sync.done` state.

**Proof required:** The new test fails on the current code and passes after the fix; a controlled real-key smoke downloads one match without exposing the key.

### BL-003 — P0 — LCU lockfile parser uses PID as port

**Location:** `backend/src/bhayanak_legends/lcu.py:106-111` (current uncommitted file)

League Client lockfiles use five fields: `process:pid:port:password:protocol`. The parser documents a four-field shape and reads `parts[1]` as the port. That field is the PID. The new `test_parse_lockfile_*` cases codify the same incorrect four-field fixture, so the backend suite stays green while production Windows parsing is wrong. See the established LCU format documented by [Hextechdocs](https://hextechdocs.dev/getting-started-with-the-lcu-api/) and the typed [`RiotLockFile`](https://docs.rs/league-client-connector/latest/league_client_connector/struct.RiotLockFile.html).

**Impact:** On Windows the bridge will connect to the process ID as if it were a TCP port and authenticate with a string containing the real port. Champ-select detection and all authenticated LCU calls fail.

**Fix:** Parse `process`, `pid`, `port`, `password`, and `protocol` explicitly; use field 3 as the port and field 4 as the password. Add a realistic lockfile fixture such as `LeagueClient:13268:63569:secret:https`. Do not infer correctness from Linux fixture replay because it bypasses lockfile parsing.

**Proof required:** Unit test asserts `port == 63569`, `token == "secret"`, and `protocol == "https"`; a Windows smoke connects to `/lol-gameflow/v1/gameflow-phase`.

### BL-004 — P1 — Progress chart overcounts Personal History and misweights win rate

**Location:** `backend/src/bhayanak_legends/routers_data.py:63-79`, `src/routes/progress.tsx:21-36`

The backend emits one rolling-window point per match and sets `games` to the size of that point's window. The frontend then sums `games`, `wins`, and `rolling_wr * games` across every overlapping point. The same matches are counted repeatedly.

**Observed with imported Personal History:** The summary reported **150 matches**, while the Progress chart claimed **202 synced games**.

**Impact:** The Improvement Journal presents incorrect personal sample sizes and a mathematically invalid aggregate win-rate line. This directly damages the product's core promise of honest personal guidance.

**Fix:** Define one unambiguous trajectory contract. Recommended: each point carries the match timestamp/index and the rolling rate for that match; the UI plots points but never sums overlapping windows. If the UI needs patch aggregates, expose a separate patch aggregate endpoint or return exactly one aggregate row per patch/role/champion. Update backend, TypeScript types, tests, and UI together.

**Proof required:** For 150 stored matches, every UI sample count remains 150 or a clearly labelled filtered subset; a multi-role/multi-champion integration test catches overlapping-window double counting.

### BL-005 — P1 — Jungle CS benchmark compares different feature definitions

**Location:** `backend/src/bhayanak_legends/extract.py:41, 76-80`, `backend/tools/build_pack.py:308-320`, `backend/src/bhayanak_legends/routers_data.py:135-151`

Personal `cs10` is `minionsKilled + jungleMinionsKilled`. Pack `cs10_median` is built from `lane_minions_first_10m`. Those are not the same feature, especially for Jungle.

**Observed:** The UI compared a personal Jungle value of **54.0** with a population median of **1**, presenting **+53.0** as if it were meaningful.

The same endpoint also maps personal `gold10` from `gold_diff_10`, which is a difference versus the all-player median, while the contract names it as absolute `gold10`.

**Impact:** Users receive prominently rendered but invalid comparisons. The numbers look precise enough to be trusted.

**Fix:** Create a feature-contract table shared by pack generation and personal extraction: exact name, unit, population column, personal extractor, eligible roles, missing-data rule, and source reference. Compare only identical definitions. For Jungle, either use total CS on both sides or suppress the card until a matching population benchmark exists. Rename gold difference fields instead of relabelling them as absolute gold.

**Proof required:** Contract test joins every personal benchmark field to the exact pack feature definition; fixture values for all five roles yield plausible same-unit comparisons.

### BL-006 — P1 — Settings can silently target a hard-coded real Riot ID

**Location:** `src/components/journal/SyncPanel.tsx:8-10, 56-65`

The form defaults to `SacredButtholio#OOF` when no Riot ID is saved. If a user pastes a valid key and starts Backfill without replacing the field, the app attempts to sync that account rather than requiring the user's identity.

**Impact:** Wrong-account Personal History can be downloaded and shown as the user's own data. It also embeds a personal identifier in production UI and tests.

**Fix:** Default to an empty field. Require and validate `GameName#TAG` before enabling Start Backfill. Keep named accounts only in test fixtures. Clear any cached PUUID when the Riot ID or region changes.

**Proof required:** Fresh install cannot start without an explicit valid Riot ID; changing the ID forces account resolution again.

### BL-007 — P1 — Riot key storage contradicts the credential-security ADR

**Location:** `backend/src/bhayanak_legends/app.py:120-123`, `backend/src/bhayanak_legends/store.py:6-10, 50-59`, ADR-0004

The Riot key is stored as plaintext in the SQLite `settings` table. ADR-0004 requires Windows DPAPI / Credential Manager for release installs.

**Impact:** Any process or backup that can read the database can recover the permanent Riot key. The UI correctly hides it on GET, but storage remains exposed.

**Fix:** Move the secret to Windows Credential Manager/DPAPI behind one credential-store module. Keep only a `has_key`/credential reference in SQLite. Ensure logs, API errors, process arguments, and release crash reports never contain the key.

**Proof required:** Database inspection cannot recover the key; save/load/delete works on Windows; tests use an injected in-memory credential store.

### BL-008 — P1 — Nullable settings cannot be cleared despite the frozen contract

**Location:** `docs/CONTRACT.md:43`, `backend/src/bhayanak_legends/models.py:19-23`, `backend/src/bhayanak_legends/app.py:114-123`

`SettingsPatch` permits `riot_id?: string | null` and `riot_key?: string | null`, but the handler only writes fields whose value is not `None`. Pydantic defaults also do not distinguish omitted from explicitly null.

**Observed:** After saving an ID and key, `PUT /settings {"riot_id": null, "riot_key": null}` returned the old ID and `has_key: true`.

**Impact:** Users cannot remove their account identifier or permanent credential through the documented API.

**Fix:** Use `patch.model_fields_set` to distinguish omitted fields from explicit null. Route key deletion through the credential store from BL-007. Add round-trip tests for set, preserve-on-omit, and clear-on-null.

### BL-009 — P1 — Personal extraction violates ADR-0001 and leaves core habits permanently unavailable

**Location:** ADR-0001, ADR-0008, `backend/src/bhayanak_legends/extract.py`, `backend/src/bhayanak_legends/routers_data.py:155-170`

ADR-0001 rejects an app-owned slim extractor because it will drift from LoLTrends. ADR-0008 vendors only the Riot client until a wheel exists. The current app nevertheless owns a slim extractor and explicitly uses a different all-player-median gold proxy. All four post-game habit outcomes are hard-coded to `value="n/a"` and `verdict="n/a"`; tests codify that placeholder.

**Impact:** Personal History fields can carry the same names as research features while meaning something else. The main post-game improvement loop never evaluates the four surviving habits.

**Fix:** Either complete the pinned LoLTrends wheel and use its extractors, or record a new ADR that explicitly supersedes ADR-0001 with a versioned shared feature contract and parity fixtures owned by both repositories. Do not ship same-named proxies. Implement habit outcomes only when their exact extractors and thresholds are available; otherwise remove the evaluative UI rather than filling it with permanent `n/a` rows.

### BL-010 — P1 — Most Findings Pack numbers have no carried provenance

**Location:** repository pack guardrail, `pack/pack.schema.json`, `pack/findings-pack.v1.json`, `backend/tools/build_pack.py`

The repository rule says every pack number carries a `source_ref`. Only finding objects support that field. A recursive audit found **203 numeric leaves: 8 traced and 195 untraced**. Habits, objectives, comeback odds, bans, tiers, matchups, benchmarks, and checkpoints do not carry row-level provenance.

The schema description weakens the rule to “source_ref or computed from the Feature Store,” but computed rows still do not identify the source snapshot, generator version, or feature definition. The generator also defaults to an absolute path under one developer's home directory.

**Impact:** Users and maintainers cannot trace most displayed population numbers to a research document or reproducible data build. This undermines the product's defining evidence boundary.

**Fix:** Resolve the rule/schema conflict explicitly. Recommended: add provenance to every numeric-bearing table row or a required table-level provenance object containing source document/section, Feature Store manifest/hash, generator revision, and feature contract version. Replace the absolute default with a required CLI argument or repository-independent configuration.

**Proof required:** Schema and tests reject any numeric table without valid provenance; a clean environment can reproduce the pack from declared inputs.

### BL-011 — P1 — Disabled scaffolds display fabricated values as if they were user state

**Location:** `src/components/progress/WhatIfPanel.tsx:1-5, 34-109`, `src/components/champ-select/LoadoutCard.tsx:1-26`

The disabled What-if panel displays `−280g`, `1 of 6`, and `62%` even though no model or user-state binding exists. The idle Loadout card displays `Electrocute` and `Flash / TP`, labels itself `WRITABLE`, and only reveals the non-functional state through a disabled button tooltip.

**Impact:** Static design-artifact values can be mistaken for personal measurements or recommendations. This conflicts with the project's evidence and completeness rules.

**Fix:** Remove fabricated values. Render an explicit unavailable state with no numeric claims until the model/live source exists. Label the loadout read-only and show values only after a champion-specific source is available.

### BL-012 — P1 — Advertised desktop/release requirements are not implemented

**Location:** ADR-0005, ADR-0006, ADR-0007, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, `src-tauri/src/lib.rs`, `.github/workflows/release.yml`, `src/components/journal/SyncPanel.tsx:151-163`

Missing consumers/implementations:

- `auto_sync` is stored and rendered but never read on startup.
- No Findings Pack release checker, compatibility validator, atomic swap, or `pack.updated` publisher exists.
- No Tauri updater dependency, plugin initialization, endpoint/public key config, or runtime check exists, although releases emit `latest.json`.
- No always-on-top call or compact champ-select/in-game window mode exists.

**Impact:** Settings and release copy promise behavior the binary cannot perform. Friends can remain on stale research/app versions, and the app does not behave as the companion window described by its ADRs.

**Fix:** Either implement each ADR end to end or relabel it as accepted future work and remove present-tense UI/release claims. Do not keep inert settings. Add release-channel integration tests against signed test metadata and pack fixtures.

### BL-013 — P1 — Desktop sidecar startup has a port race and no readiness contract

**Location:** `src-tauri/src/lib.rs:46-49, 63-87, 96-105`

Tauri binds port 0 to discover a free port, closes the listener, then starts Python later on that port. Another process can claim it in between. Tauri stores and returns sidecar info immediately after process spawn without waiting for `/health`; a process that exits during import/bind still leaves the webview to discover the failure through fetch retries. There is no restart path.

**Impact:** Startup is intermittently offline and difficult to diagnose. This becomes more likely on busy Windows machines or when a previous sidecar is still exiting.

**Fix:** Introduce a supervised readiness handshake. Prefer having the sidecar bind its own ephemeral port and report the actual port over captured stdout/IPC. Tauri should wait for an authenticated readiness response, detect early exit, retry a bounded number of times, and expose a structured startup error to the UI.

### BL-014 — P1 — Desktop webview hardening is disabled

**Location:** `src-tauri/tauri.conf.json:22-24`, `src-tauri/capabilities/default.json`, `index.html:5-10`, `src-tauri/src/lib.rs:93-94`

The Tauri CSP is `null`. The app loads Google Fonts at runtime, retains the template Vite favicon/title, initializes the opener plugin, and grants `opener:default` even though no frontend opener use was found.

**Impact:** Any future HTML/script injection has fewer containment layers around a webview that can retrieve the sidecar token and invoke native plugins. Remote font requests also weaken offline/privacy expectations.

**Fix:** Bundle fonts locally, set a restrictive Tauri CSP with only required loopback `connect-src`, remove the unused opener plugin/capability, and set product metadata. Keep shell permission restricted to the named sidecar.

### BL-015 — P1 — Frozen API/SSE contracts drift from runtime shapes

**Location:** `docs/CONTRACT.md:7, 31-97`, `backend/src/bhayanak_legends/models.py`, `backend/src/bhayanak_legends/app.py:95-101`, `backend/src/bhayanak_legends/routers_events.py:9-17`, current `live.py`

Examples:

- The contract says all HTTP requires a token except `/events`; `/health` is unauthenticated.
- Frontend `Health.pack_version` is a string; backend allows and returns null when the pack is unavailable while still reporting `status: "ok"`.
- SSE `hello` requires both app and pack version; runtime omits pack version.
- Backend Pydantic models use broad strings/dicts rather than the contract's literals and fixed nested structures.
- Rich live contract/types/routes are present, but `hooks.ts` duplicates the API request path and can issue a cold-load request with an unresolved base/token instead of using `client.ts`.

**Impact:** TypeScript can believe invalid data, consumers cannot reason from the documented protocol, and degraded startup can look healthy.

**Fix:** Treat contract, Pydantic models, response models, TypeScript types, and integration fixtures as one change boundary. Add response models to routes and literal/enumeration validation. Use a degraded/unready health state when pack or mandatory services fail.

### BL-016 — P1 — UI misses WCAG AA and breaks at the documented minimum width

**Location:** `src/styles.css:10-12`, `src/design-system.css:52-67`, fixed route grids, `src-tauri/tauri.conf.json:18`

Measured findings:

- `--color-dim` renders at **3.58:1–4.07:1** over common surfaces; `--color-dimmer` renders at **2.34:1–2.45:1**. Both are used for 8–11px text. Normal text requires 4.5:1 under WCAG 1.4.3.
- The Live page contained **196 text-bearing elements below 12px** at 1280×820.
- All six top-nav links measured **23px high**; every interactive target on Live was below 44px in at least one dimension.
- At the configured 980px minimum window width, Champ Select had a **965px client width and 1056px scroll width**, with 27 elements extending past the right viewport edge.
- Layout uses generic `div` wrappers instead of `header`/`nav`/`main`; connection status is communicated primarily by a colored dot/title.

**Impact:** Low-vision users cannot reliably read supporting text, keyboard/screen-reader structure is weak, and the minimum supported window clips a primary workflow.

**Fix:** Raise text size/contrast, reserve dimmer tokens for non-text decoration, add semantic landmarks and live status text, establish visible `:focus-visible` styles, meet target-size guidance, and add responsive/compact grid breakpoints at and above 980px.

### BL-017 — P2 — Patch ranges are sorted lexicographically

**Location:** `backend/src/bhayanak_legends/routers_data.py:25`, `src/routes/history.tsx:86-90`

The backend sorts strings, so patch `16.10` precedes `16.9`. The current UI displayed `16.10 → 16.9` for a history that actually spans 16.5 through 16.16.

**Fix:** Sort parsed numeric `(major, minor)` tuples in the backend and share/test the ordering rule. Include 16.9/16.10 in a regression test.

### BL-018 — P2 — API errors lose the only actionable detail

**Location:** `src/api/client.ts:23-35`, route error copy

The client throws only `METHOD path -> status` and discards JSON `{detail}`. UI messages therefore collapse bad credentials, invalid Riot IDs, pack validation failure, and an offline sidecar into generic “sidecar offline” copy.

**Impact:** Users cannot correct their input, and support cannot distinguish configuration from infrastructure failures.

**Fix:** Parse a bounded error body into a typed `ApiError` with status and safe detail. Map known errors to specific UI actions; keep unknown server text out of logs if it could contain sensitive input.

### BL-019 — P2 — SSE ownership and live rendering do unnecessary work

**Location:** `src/components/Layout.tsx:14-16`, route-level `useEvents()` calls, `src/api/sse.ts`, `src/routes/live-match.tsx:21-39`

Layout opens an SSE connection solely for the connection dot, while active routes open another; History adds a route-local subscriber through `SyncPanel`. The in-game clock updates state every 500ms in the page component, rerendering the whole dense dashboard even though only clock-dependent elements change.

**Impact:** Duplicate sockets/reconnect timers and avoidable full-page renders increase failure modes in a long-running companion app.

**Fix:** Own one EventSource in an app-level provider/store and fan out typed events internally. Isolate the local clock in a small component or external store that only updates clock consumers. Validate event data instead of unchecked casts.

### BL-020 — P2 — Test gates pass shallow surfaces and miss the critical seams

**Location:** `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `e2e/smoke.spec.ts`, backend sync/live tests, frontend tests

Gaps:

- No test covers the real Riot Backfill orchestration; import-only tests missed BL-002.
- Existing E2E checks visibility and route navigation against a separately running web sidecar; it does not package/start the current Tauri binary or replay active live sessions.
- Release runs on tags and publishes directly without first running the four repository gates; tag pushes do not match the CI branch trigger.
- The frontend suite passes with **four React `act(...)` warnings** from live-clock tests.
- No Rust vulnerability audit tool is configured; `cargo-audit` was unavailable during this review.
- GitHub Actions use mutable major-version tags instead of immutable SHAs despite access to release-signing secrets.

**Impact:** Green CI does not establish that the Windows release starts, syncs, receives live data, or updates safely.

**Fix:** Add seam tests, make release depend on a reusable verified workflow, smoke the packaged sidecar/Tauri app on Windows, pin actions by commit SHA, and make test warnings fail CI where practical.

## UI technical audit

### Audit Health Score

| Dimension | Score (0–4) | Key finding |
|---|---:|---|
| Accessibility | 1 | Low-contrast 8–11px text and weak semantics |
| Performance | 3 | Small bundle, but duplicate SSE and full-page 2Hz clock renders |
| Theming | 2 | Good token base; many hard-coded colors and no CSP-compatible local fonts |
| Responsive design | 1 | Desktop-only fixed grids; Champ Select overflows at the configured minimum width |
| Implementation integrity | 2 | Product-specific visual system, but fabricated disabled values and many placeholder panels |
| **Total** | **9/20 — Poor** | **Major usability and truthfulness work remains** |

The bundled Impeccable detector returned no deterministic violations. Manual/runtime checks still found the issues above; the detector result is not a WCAG or product-truth pass.

## Positive findings to preserve

- Domain terms are explicit and consistently documented in `CONTEXT.md`.
- The process split is sensible: thin Rust shell, Python domain logic, React presentation.
- Frontend API access is centralized; no direct route-level `fetch` was found.
- Loopback binding, random per-launch token generation, and constant-time token comparison are sound baseline controls.
- Personal History is local SQLite data and no code path uploads it.
- SQL uses parameters and access is serialized with a re-entrant lock.
- The Findings Pack is schema-validated and diagnostic phrasing has dedicated tests.
- TypeScript is strict with unused-symbol checks.
- Champ-select enemy names are intentionally excluded, and enemy ability/ultimate timers are not implemented.
- The isolated folder-import smoke successfully ingested 150 matches and produced summary, benchmark, trajectory, and post-game responses.
- `pnpm audit --prod` and Python `pip-audit` found no known vulnerabilities at audit time.
- Rust compiled successfully before the concurrent backend-only live changes.
- The UI has a distinctive, coherent, product-specific visual language despite its accessibility and placeholder problems.

## Recommended fix sequence

1. **Stabilize the live cutover.** Restore frontend build/tests, correct lockfile parsing, centralize rich snapshot requests in `client.ts`, and add active-session browser coverage.
2. **Repair core data paths.** Fix the Riot fetcher, add real-flow tests, validate Riot ID/key behavior, and make Backfill genuinely resumable across eras.
3. **Restore metric truth.** Establish one shared feature contract, fix trajectory aggregation, suppress incompatible benchmarks, sort patches numerically, and remove fabricated values.
4. **Secure local secrets and the webview.** Implement Credential Manager/DPAPI, CSP, bundled fonts, minimal native capabilities, token-safe logging, and sidecar readiness supervision.
5. **Align contracts and scope.** Update contract/Pydantic/TypeScript/SSE fixtures atomically. Remove inert UI/settings or implement the ADRs they promise.
6. **Make releases prove themselves.** Gate tag publishing on all tests, package smoke on Windows, configure the Tauri updater, validate atomic pack updates, and pin workflow actions.
7. **Run an accessibility/compact-window pass.** Fix contrast/type scale, landmarks/focus/status semantics, target sizes, and 980px/companion-window layouts.

## Verification evidence

### Latest current-tree results

- `cd backend && uv run pytest -q` — **64 passed, 1 deprecation warning**.
- `pnpm vitest run` — **failed: 2 files, 6 tests failed, 49 passed**, plus one unhandled `PlayerList` exception.
- `pnpm build` — **failed: exit 2**, with four TypeScript errors in `YourSideCard.tsx`.

### Additional checks

- Earlier backend baseline: **46 passed, 1 deprecation warning** before the live-bridge tests were added.
- Earlier frontend baseline: **7 files, 55 tests passed**, with four React `act(...)` warnings, before the rich UI cutover.
- Earlier production build: passed; JS **404.29 kB / 117.95 kB gzip**, before the rich UI cutover.
- `pnpm exec playwright test` — **8 passed** against the older already-running sidecar on `127.0.0.1:23110`.
- `cd src-tauri && cargo check` — passed.
- `pnpm audit --prod` — no known vulnerabilities.
- `uvx pip-audit --path backend/.venv/lib/python3.13/site-packages` — no known third-party vulnerabilities; the local package is not on PyPI and was skipped.
- `cargo-audit` — not run; tool not installed.

The E2E pass does **not** validate the current rich backend/frontend protocol because it reused an older sidecar process and only checks idle/visibility paths.

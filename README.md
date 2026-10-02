# Bhayanak Legends

A League of Legends companion with a local Improvement Journal and Findings Pack population context from [LoLTrends](https://github.com/theHimanshuShekhar/lol-trends). V1 supports the browser web view with a local FastAPI sidecar. The Tauri Windows shell and release tooling remain in the repository; native packaging and publication are outside this v1 acceptance scope.

Personal History stays on this machine and is scoped to the resolved Riot account. Population findings come only from the versioned Findings Pack, with their own samples, patch scopes, and caveats. Population associations describe observations; they do not guarantee an outcome.

## Available flows

- **Improvement Journal:** account/key settings, resumable era-first Backfill, role/champion filters, recent results, and measured feature observations with explicit missing-data states.
- **Trajectory:** true match counts and patch win rates, with links to personal reviews. **Champions:** population role tiers, declared matchup evidence, and a selected champion's local rolling Trajectory.
- **Post-game Review:** latest synced match, available checkpoints, bounded personal observations, and clearly separated population context. It updates through Backfill; a live game ending alone does not download a digest.
- **Live Companion:** official-shaped champ-select roster, bans, role, pick/lock evidence, timer, and in-game scores, inventory, events, and clock. Enemy summoner names are stripped from champ select.

Canonical Findings Pack v7 withholds both Live WP and Personal What-If pending corrected training/validation. Compatible checkpoint Benchmarks and automatic habit verdicts are unavailable with the current evidence. The app keeps personal observations useful without filling these gaps with guesses. No champion-specific loadout or gameplan is advertised.

## Browser development

Prerequisites: Node 24, pnpm 11, and [uv](https://docs.astral.sh/uv/). Run from the repository root:

```bash
pnpm install --frozen-lockfile
uv sync --project backend --frozen
```

Start the sidecar in one terminal:

```bash
export BHAYANAK_TOKEN='local-development-token-change-me-32chars'
BHAYANAK_PORT=23110 uv run --project backend python -m bhayanak_legends.sidecar
```

Start the browser UI in another terminal, using exactly the same local token:

```bash
VITE_BL_PORT=23110 VITE_BL_TOKEN='local-development-token-change-me-32chars' pnpm dev
```

Open the printed Vite address (normally `http://localhost:1420`). The local token authenticates the browser to the sidecar; it is separate from the Riot API key. `BHAYANAK_TOKEN` and `VITE_BL_TOKEN` must be set to the same value; a Riot API key is needed for Backfill. Save your Riot ID, regional match route, and personal Riot key in the Improvement Journal to start Backfill. Saving settings alone does not validate the key against Riot; account resolution and sync show their own status and retry feedback. Account lookup can try other regional account routes; match downloads use the selected match route.

Development import is optional and debug-only. To enable it, create an approved local folder first, then supply `BHAYANAK_ALLOW_IMPORT=true` and `BHAYANAK_IMPORT_ROOTS` as a JSON list of existing canonical directory paths. `POST /dev/import {"dir":"..."}` accepts only folders under those roots. Import is not a production onboarding flow.

## Verification

Run each command from the repository root:

```bash
uv run --project backend pytest backend/tests -q
pnpm vitest run
pnpm build
pnpm exec playwright test
```

Playwright starts its own isolated sidecars, LCU/Live Client Data replay services, and Vite server. Do not start a separate sidecar for it. Fixtures include official integer bans and a JSON-string LCU version; Live Client Data omits nonofficial game ID/version fields. Synthetic available-model fixtures test mechanics only and do not constitute release evidence.

See [v1 acceptance](docs/v1-acceptance.md) for supported scope and current validation, [CONTEXT.md](CONTEXT.md) for terminology, [the interface contract](docs/CONTRACT.md), and [architecture decisions](docs/adr/). Historical visual proposals in [design-deltas.md](docs/design-deltas.md) are archived.

## Native releases

Existing Windows build, signing, updater, and Findings Pack release workflows are documented in [docs/workflows.md](docs/workflows.md). Running those workflows, native Windows smoke testing, a real League session, and live Riot API validation are deferred from this web-view v1 acceptance. No release is published by completing the local gates.

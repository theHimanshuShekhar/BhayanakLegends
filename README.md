# Bhayanak Legends

A Windows 11 companion app for League of Legends that turns the [LoLTrends](https://github.com/theHimanshuShekhar/lol-trends) research into personal guidance: live advice during champ select and games, plus an Improvement Journal built from your own match history.

Friends-first by design: every population number is learned from the friend group's ~26k games, your Personal History never leaves your machine, and advice phrasing follows the research's Actionable/Diagnostic discipline.

## Screens

- **Live Companion** — champ select intel (ban advisor, mastery premium, counterpick honesty) and in-game objective priors; live win-probability arrives with the first model-bearing Findings Pack.
- **Improvement Journal** — post-game digests, patch-over-patch trajectory, champion tier lists, and the era-first Backfill that fills your Personal History from the Riot API.

## Architecture

Tauri 2 shell → spawns a PyInstaller-packaged **FastAPI sidecar** on loopback (port + token negotiated at spawn). The webview talks REST + SSE to the sidecar only. Population numbers and model artifacts come from the versioned **Findings Pack** (LoLTrends' only obligation); personal features are extracted from match/timeline JSONs on-device. Decisions: [docs/adr/](docs/adr/) · glossary: [CONTEXT.md](CONTEXT.md) · interfaces: [docs/CONTRACT.md](docs/CONTRACT.md).

## Development

Prereqs: Node 24 + pnpm 11, Rust (tauri), [uv](https://docs.astral.sh/uv/).

```bash
pnpm install
cd backend && uv sync

# sidecar (dev token)
BHAYANAK_PORT=23110 BHAYANAK_TOKEN=dev uv run python -m bhayanak_legends.sidecar &

# frontend against the sidecar
cd .. && VITE_BL_PORT=23110 VITE_BL_TOKEN=dev pnpm dev

# or the full desktop shell (spawns the sidecar itself)
pnpm tauri dev
```

Dev match data: point the app's import endpoint at a LoLTrends-layout folder (`POST /dev/import {dir}`), or run a real sync from the History screen with your own Riot personal key.

## Testing

```bash
cd backend && uv run pytest -q      # unit + integration
pnpm vitest run                     # component tests
pnpm exec playwright test           # e2e against dev server + sidecar
pnpm build                          # typecheck + bundle
```

## Releases

Tag a `v*` push: GitHub Actions builds the Windows installer + signed auto-update feed via tauri-action ([docs/adr/0007](docs/adr/0007-public-release-channel-tauri-updater.md)). Repo secrets required: `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.

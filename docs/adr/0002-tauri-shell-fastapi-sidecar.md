# Tauri shell talks to a FastAPI sidecar over loopback HTTP + SSE

The Windows app is a Tauri 2 shell whose UI (React 19 + TypeScript + Vite + Tailwind) never touches Riot APIs or loltrends directly. Tauri spawns a PyInstaller-packaged FastAPI binary as a sidecar on `127.0.0.1` with an ephemeral port and auth token; reads go over REST, live-game updates (LCU events, in-game polls) stream to the UI via SSE. All logic lives in Python next to the loltrends dependency; Rust stays a thin window/process shell.

## Considered Options

- **stdio JSON-RPC sidecar** (rejected): no open ports, but hand-rolled event multiplexing for live pushes and loss of HTTP tooling.
- **Thick Rust, thin Python** (rejected): splits client plumbing across two languages and rebuilds LCU/live-client handling from scratch.

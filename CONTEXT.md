# Bhayanak Legends

A League of Legends companion for personal match review and clearly labeled LoLTrends population context. The Improvement Journal describes Personal History; the Live Companion mirrors observed champ-select and in-game state.

## Language

### Sources

**Findings Pack**:
The versioned export of population findings (effect sizes, thresholds, caveats) and model artifacts produced by LoLTrends; the app's only source of population-level numbers and live-inference models.
_Avoid_: research data, feature store

**Personal History**:
The local user's own matches downloaded from the Riot API and extracted into per-match feature shards on their machine. Never leaves the machine; never mixes with the Findings Pack's population data.
_Avoid_: match cache, user data

**Live Companion**:
The app screen covering observed champ-select and in-game state, with separately labeled Findings Pack population context.
_Avoid_: live screen, overlay (reserved for overlay frameworks we don't use)

**Improvement Journal**:
The app screen covering historical strengths, weaknesses, and post-game digests.
_Avoid_: history screen, stats page

### Sync

**Backfill**:
The era-first historical download that fills Personal History: current-patch-era games first, older matches continuing in the background across sessions from a resumable queue.
_Avoid_: initial sync, bulk download

### Comparison

**Benchmark**:
A Findings Pack population median shown beside the user's own value for the same feature and role; a comparison is valid only when both sides use the identical feature definition.
_Avoid_: baseline, average

**Trajectory**:
The per-match rolling win-rate line across a player's Personal History.
_Avoid_: progress chart, trend line

### Hosting

**Sidecar**:
The local FastAPI companion process spawned and supervised by the Tauri shell; the webview's only backend.
_Avoid_: backend, server

**Recall Measurement Revision**: The version of bounded recall observation and missing-data semantics. An obsolete revision cannot supply current recall values or authorize predictive inference.

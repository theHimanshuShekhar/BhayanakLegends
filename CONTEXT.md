# Bhayanak Legends

A Windows companion app for League of Legends that turns the LoLTrends research into personal guidance: live advice during champ select and games, plus a historical improvement journal.

## Language

### Sources

**Findings Pack**:
The versioned export of population findings (effect sizes, thresholds, caveats) and model artifacts produced by LoLTrends; the app's only source of population-level numbers and live-inference models.
_Avoid_: research data, feature store

**Personal History**:
The local user's own matches downloaded from the Riot API and extracted into per-match feature shards on their machine. Never leaves the machine; never mixes with the Findings Pack's population data.
_Avoid_: match cache, user data

**Live Companion**:
The app screen covering champ select and in-game advice.
_Avoid_: live screen, overlay (reserved for overlay frameworks we don't use)

**Improvement Journal**:
The app screen covering historical strengths, weaknesses, and post-game digests.
_Avoid_: history screen, stats page

### Sync

**Backfill**:
The era-first historical download that fills Personal History: current-patch-era games first, older matches continuing in the background across sessions from a resumable queue.
_Avoid_: initial sync, bulk download

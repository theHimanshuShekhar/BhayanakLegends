# Vendor a stdlib-mirror of the Riot seeding client until loltrends ships a wheel

ADR-0001 wants the app to depend on `loltrends` as a pinned library for match fetching. That dependency is not yet installable in the sidecar context: LoLTrends publishes no distribution, and importing it in place would drag pandas/streamlit-grade dependencies into a binary that must stay lean. Until a wheel exists, `backend/src/bhayanak_legends/riot_client.py` mirrors the semantics of `loltrends.etl.contrast.RiotSeedingClient` (rate limiting 20/s + 100/120s, 429 Retry-After backoff, match-id pagination, match/timeline fetch) behind a compatible interface, so the swap to the real pinned dependency is a constructor change.

## Consequences

- The mirror is the single place to delete when the dependency lands; its docstring references this ADR.
- One deliberate divergence: every request sends a custom User-Agent because Riot's sea route rejects the default Python one with 403.

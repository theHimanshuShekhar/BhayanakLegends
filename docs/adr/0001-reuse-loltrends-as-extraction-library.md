# Reuse loltrends as a pinned library for personal-match extraction

The app downloads its user's match history via the Riot API and must extract features (recall safety, checkpoints, wave-state proxies, etc.) from raw match/timeline JSON. Reimplementing those extractors would risk silent definitional drift from the research, so the app depends on `loltrends` directly — pinned to a git tag, upgraded deliberately. This is a code-level contract that complements the Findings Pack's data-level contract; it does not reopen ADR-0004 in the LoLTrends repo (the app still never reads the Feature Store or raw research parquet).

## Considered Options

- **App-owned slim extractor** (rejected): full repo separation, but duplicates hard, tested logic and invites drift between "same-named" features computed differently across repos.
- **Pack carries precomputed personal data** (rejected): contradicts the product requirement that every friend's app fetches and analyzes their own history on their machine.

## Consequences

- The app calls loltrends' per-match extraction internals only; never `build-feature-store`, never Feature Store paths.
- Findings interpretation comes exclusively from the Findings Pack; the library contributes extraction, not conclusions.

# Pack delivery: bundled baseline + public GitHub Releases channel

Installs ship with the current Findings Pack bundled, so the app works offline
on first run. On launch the sidecar checks this public repository's
unauthenticated release manifest
(`releases/latest/download/findings-pack-manifest.json`) for a newer pack
version. Private LoLTrends CI publishes the pack asset into this repository's
release; the installed app never carries a GitHub token (ADR-0007).

The sidecar downloads a candidate to a temporary location, validates schema and
feature-contract versions, required model artifacts and their declared hashes,
and app compatibility, then atomically replaces the active pack. Network
failure, truncation, corruption, incompatibility, or an interrupted replace
leaves the bundled/current pack untouched and usable.

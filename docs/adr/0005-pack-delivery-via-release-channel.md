# Pack delivery: immutable bundled seed + durable active release

Installs ship with the current Findings Pack bundled as a read-only first-run
seed, so the app works offline on first launch. The sidecar validates that seed
and atomically commits it to the per-user active directory
`<data_dir>/findings-pack/active`. The installation bundle (including a frozen
PyInstaller `_MEIPASS` directory) is never a runtime write destination.

On launch the sidecar checks this public repository's unauthenticated release
manifest (`releases/latest/download/findings-pack-manifest.json`) for a newer
pack version. Private LoLTrends CI publishes the pack asset into this
repository's release; the installed app never carries a GitHub token (ADR-0007).

The sidecar downloads a candidate to a temporary sibling location, validates
schema and feature-contract versions, required model artifacts and their
declared hashes, and app compatibility, then atomically replaces the active
pack. Network failure, truncation, corruption, incompatibility, or an
interrupted replace leaves the previously active pack untouched and usable.
An existing active pack always wins over a changed bundled seed after an
application upgrade.

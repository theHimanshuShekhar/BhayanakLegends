# Pack delivery: bundled baseline + GitHub Releases update channel

Installs ship with the current Findings Pack bundled, so the app works offline on first run. On launch the sidecar checks LoLTrends' GitHub Releases for a newer pack version, downloads it, validates `schema_version` plus model-artifact compatibility against the feature contract, and swaps it in atomically. This makes research iterations reach friends without re-shipping installers, while never leaving an install broken by a bad or partial download.

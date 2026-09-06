# Pack delivery: immutable bundled seed + authenticated public release channel

Installs ship with the current Findings Pack bundled as a read-only first-run
seed, so the app works offline on first launch. The sidecar validates that seed
and atomically commits it to the per-user active directory
`<data_dir>/findings-pack/active`. The installation bundle (including a frozen
PyInstaller `_MEIPASS` directory) is never a runtime write destination.

On launch the sidecar checks this repository's public release manifest
(`releases/latest/download/findings-pack-manifest.json`) for a newer pack. The
latest route is only a locator: the first successful immutable GitHub tag
redirect becomes the logical release URL. Subsequent manifest, detached
signature, and payload requests remain pinned to that repository/tag/asset; a
GitHub release may transfer through only the exact
`release-assets.githubusercontent.com` CDN on HTTPS port 443. Private LoLTrends
CI publishes the pack asset and its detached
`findings-pack-manifest.json.sig` signature into this repository's release. The
installed app never carries a GitHub token (ADR-0007).

The sidecar authenticates the exact raw manifest response bytes with the pinned
Ed25519 public key before decoding JSON. The manifest is bounded to 256 KiB and
the detached signature to 16 KiB. A manifest payload reference is relative and
confined beneath the pinned logical release path; sibling URLs, userinfo,
queries, fragments, cross-origin redirects, and CDN starts are rejected.
HTTPS is required for the manifest, signature, asset, and every redirect hop.
The only exception is an explicitly enabled literal `http://127.0.0.1` fixture
URL; that mode remains origin-pinned and is never inferred from a hostname
alias or an external environment.

CI supplies the private signing seed only through the owner-provisioned
`FINDINGS_PACK_MANIFEST_SIGNING_KEY` secret. The local seed generated for
release setup is kept under the ignored `backend/.signing/` directory and is
never committed; `tools/sign_findings_pack_manifest.py` signs the exact bytes
emitted as `findings-pack-manifest.json`. Releases fail closed until the owner
provisions that CI secret:
`gh secret set FINDINGS_PACK_MANIFEST_SIGNING_KEY < backend/.signing/manifest-key.hex`.
The public key is pinned in the sidecar and changes only with an application
release, so rotation currently requires an app release; a two-key current/next
allowlist is an accepted follow-up. The packaged Windows smoke may supply an
ephemeral public key only alongside its literal loopback manifest URL.

The active bundle is a discriminated Findings Pack contract. Releases use
`findings-pack.v2.json` and validate the v2 model, provenance, feature-contract
versions, truthful availability states, declared ONNX artifacts/model cards,
their hashes and sizes, and app compatibility. The sidecar accepts only schema
2 and this v2 pack filename.

The sidecar downloads a candidate to a temporary sibling location, validates
the complete archive before the single pack-file commit, and atomically replaces
the active pack. Network failure, authentication failure, truncation,
corruption, incompatibility, or an interrupted replace leaves the previously
active pack untouched and usable. An existing active pack always wins over a
changed bundled seed after an application upgrade.

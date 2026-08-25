# Pack delivery: immutable bundled seed + authenticated public release channel

Installs ship with the current Findings Pack bundled as a read-only first-run
seed, so the app works offline on first launch. The sidecar validates that seed
and atomically commits it to the per-user active directory
`<data_dir>/findings-pack/active`. The installation bundle (including a frozen
PyInstaller `_MEIPASS` directory) is never a runtime write destination.

On launch the sidecar checks this repository's unauthenticated release manifest
(`releases/latest/download/findings-pack-manifest.json`) for a newer pack.
Private LoLTrends CI publishes the pack asset and its detached
`findings-pack-manifest.json.sig` signature into this repository's release; the
installed app never carries a GitHub token (ADR-0007).

The sidecar authenticates the exact raw manifest response bytes with the pinned
Ed25519 public key before decoding JSON. The manifest is bounded to 256 KiB and
the detached signature to 16 KiB. The manifest asset reference must be relative
and resolve to the manifest's scheme, host, and effective port. HTTPS is
required for the manifest, signature, asset, and every redirect hop. The only
exception is an explicitly enabled literal `127.0.0.1` URL; redirects in that
mode must remain on literal loopback.

CI supplies the private signing seed only through the owner-provisioned
`FINDINGS_PACK_MANIFEST_SIGNING_KEY` secret. The local seed generated for
release setup is kept under the ignored `backend/.signing/` directory and is
never committed; `tools/sign_findings_pack_manifest.py` signs the exact bytes
emitted as `findings-pack-manifest.json`. Releases fail closed until the owner
provisions that CI secret:
`gh secret set FINDINGS_PACK_MANIFEST_SIGNING_KEY < backend/.signing/manifest-key.hex`.
The public key is pinned in the sidecar and changes only with an application
release, so rotation currently requires an app release; a two-key current/next
allowlist is an accepted follow-up.

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

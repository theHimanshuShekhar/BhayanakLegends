# Release workflow policy

`.github/workflows/verify.yml` is the reusable required-check workflow. It runs
backend pytest, frontend Vitest, the production frontend build, Playwright
against a sidecar on `127.0.0.1:23110`, and dependency audits. The CI sidecar
uses the explicit non-production token
`BHAYANAK_TOKEN=local-sidecar-development-token-32chars`, `BHAYANAK_ALLOW_IMPORT=true`,
and a JSON-array `BHAYANAK_IMPORT_ROOTS` rooted at `data/dev-import`;
`backend/tools/ci_seed.py` creates deterministic Personal History only when
`data/dev-import` is absent.

## Packaged Windows smoke

`.github/workflows/windows-smoke.yml` is a reusable, non-publishing gate. It
checks out `${{ github.sha }}` on `windows-latest`, builds the one-file
PyInstaller sidecar with exactly
`uv run --project backend --locked python tools/build_windows_sidecar.py`, then
builds and installs a lower-version NSIS application under `${{ runner.temp }}`.
It never runs Tauri dev mode and it does not receive Riot, production updater,
or release credentials.

The smoke creates a job-local updater keypair and keeps the private key and
password in the runner's temporary workspace/environment only. It builds a
genuinely signed higher-version NSIS updater archive with
`createUpdaterArtifacts: true`, retains the emitted detached signature, and
serves those exact files from `tools/windows_updater_fixture.py`. The fixture
copies the checked-in diagnostic Findings Pack v2 seed through the
consumer-side bridge (`--bootstrap`), then archives every seed file
byte-for-byte (including each available model and its model card). It never
builds population metrics, changes `pack_version`, or substitutes an empty
`required_model_artifacts` list. Production pack assets must instead be
supplied explicitly with `backend/tools/build_pack.py --artifact
<LoLTrends-exported-artifact>`.
The bridge validates the artifact against the canonical companion schema and
fails closed on a cross-repo shape mismatch; it never translates an upstream
catalog or Feature Store export. The fixture signs a deterministic manifest
key over the exact canonical pack bytes and serves the manifest, detached
signature, and payload. It records path-only requests, advertises the valid
higher version first, then advertises a second higher version whose artifact
bytes were changed without changing the detached signature.
`tools/findings_pack_payload.py` is shared by the release builder and this
fixture so local tests cannot silently drift from the signed payload.
`tools/patch_updater_endpoint.py` temporarily replaces the endpoint, paired
public key, app version, and smoke-only
`dangerousInsecureTransportProtocol` setting; the workflow restores the
production endpoint, public key, version, and transport flag in an
unconditional cleanup step.

`tools/windows_packaged_smoke.mjs` connects to the packaged WebView2 through
the runner-local CDP port and asserts an authenticated ephemeral sidecar,
using the token returned by the `sidecar_info` handshake rather than a
hard-coded development token. It fetches `/pack`, checks the exact canonical
pack version/schema, inventories every declared available model/card, and
relies on startup's strict ONNX smoke validation (with a What-If request when
Personal History is available) rather than accepting a declaration-only model
fixture. It then asserts the existing user-facing `Install update` action.
The valid phase proves signed download/verification and waits for
`ready-to-restart`. The PowerShell harness closes and relaunches the installed
executable, proves its file version changed to the higher version, then runs
the mismatched-signature phase. That phase requires explicit signature
rejection, unchanged installed files/version, and a healthy sidecar after the
rejection. Startup failures are written to structured `smoke-state.json`
without leaving owned sidecars behind.

`tools/check_windows_smoke_fixture.py` requires valid metadata and artifact
requests, mismatched metadata and rejected-artifact requests, Findings Pack
requests, path-only diagnostics, and routes matching the fixture state. On
failure, `tools/redact_diagnostics.py` removes private-key, password,
production/public-key, Riot-key, bearer-token, and token-shaped values before
upload; key-material files become a fixed marker. The key files and production
configuration backup are outside the diagnostics tree and are removed during
cleanup. `release.yml` has `publish.needs: [verify, packaged-smoke]`, so a tag
cannot publish unless this packaged gate succeeds.

The Windows runner is required to prove the remaining acceptance criteria:
Linux cannot execute the NSIS installer, WebView2 CDP session, Tauri shell
command, or Windows child-process cleanup. Local verification is limited to
YAML parsing, immutable action-pin checks, Python/Node helper syntax, the
reversible endpoint patch, and the fixture request-state checker. A successful
authorized Windows run is still required as operational evidence for signed
install/relaunch, dynamic WebView rendering, mismatched-signature rejection,
and owned-sidecar cleanup; this repository does not dispatch that run
automatically.

## Findings Pack release publisher

On a `v*` tag, `release.yml` consumes the checked-in companion
`pack/` directory and runs
`tools/build_findings_pack_release.py`. That consumer-side builder validates
schema, semantics, and all declared ONNX/card bytes, then writes a deterministic
`findings-pack.v2.zip` and a manifest containing the Pack v2 version, minimum
app version, flattened feature-contract versions, payload size/hash, and every
available model/card pin. The manifest is always generated; it is never
conditionally skipped because a stale checked-in manifest cannot describe a
new pack. The manifest is signed over its exact bytes with the
owner-provisioned `FINDINGS_PACK_MANIFEST_SIGNING_KEY`; the key is not bundled.

The release job first checks that the `v*` tag resolves to the checked-out
commit, that its version matches both package manifests, and that no release
already exists for the immutable tag. It inventories the complete generated
updater set, then sends a token-authenticated `POST` to the Releases API with
the tag, target commit, and `draft=true`. The response is validated and its
release ID is captured as the run's release identity.

The Windows build may emit either the observed signed installer executable or
a separate unsigned installer plus signed NSIS updater archive. Staging
requires exactly one signed `.exe` or `.nsis.zip` candidate. A signed
installer executable is staged once as
`bhayanak-legends-${VERSION}-windows-x86_64-setup.exe` with its detached
signature; a separate signed archive is staged alongside the canonical
installer. The inventory records a unique asset list, so the signed-executable
case cannot upload the same file twice.

Every asset upload uses the draft response's validated `upload_url` base. The
URL must be HTTPS on `uploads.github.com`, with the exact
`/repos/<repository>/releases/<release-id>/assets{?name,label}` shape. The
workflow derives one canonical MSYS runner-temp root, converts it once to a
forward-slash native path, and passes the native inventory, identity, and asset
paths to one Python upload transaction. That transaction validates the tag,
release ID, draft state, empty asset list, safe names, and every local file
before sending each exact file's bytes to the validated upload URL. The bearer
token remains in the Python process environment and is never printed. The
workflow never sends an asset `POST` to the default API host or overwrites an
existing asset.

Before promotion, the workflow keeps the release private as a draft and queries
the captured release ID for its asset list. Because the Releases API may be
eventually consistent immediately after upload, it retries only a valid strict
subset of the expected names, using a fixed 30-second deadline and 2-second
backoff; unexpected, duplicate, malformed, or extra assets fail immediately.
It records every remote asset ID, then downloads the exact draft assets through
the asset-ID endpoint.
Immediately before promotion, it re-fetches the captured release's assets and
requires the exact persisted name-to-asset-ID map; any mutation aborts the
promotion.
The existing updater checker validates the remote archive relationship, while
the workflow verifies the pinned updater Minisign key, the complete four-line
detached-signature box (including its prehashed primary and global signature),
release-tag URL, version, manifest signature, payload hash, and exact
local/remote Findings Pack bytes. Only that complete verification permits a
`PATCH` to the captured release ID with `draft=false`. No post-creation release
mutation is addressed by tag.

The final step fetches the stable `latest` updater and Findings Pack endpoints
anonymously over HTTPS, cryptographically re-verifies the updater signature
against the pinned key, and repeats the consumer-facing version, signature,
and hash checks. If any later step fails after this run creates the owned
draft—including an ambiguous response from the promotion request—the recovery
step requires the pre-mutation promotion-attempt marker, verifies the current
release ID, and re-drafts only that same release when it is public; it no-ops
while the release is still a draft.
Installed clients use only the public
`releases/latest/download/findings-pack-manifest.json` locator; they carry no
GitHub token. The sidecar resolves `latest` through a bounded same-repository
`github.com` tag redirect, pins the logical tag URL, and
fetches the tagged manifest/signature/payload (allowing only GitHub's bounded
CDN transfer redirect). It authenticates the raw manifest before parsing it and
validates the complete candidate before PackStore atomically swaps its
generation pointer.

## Windows release shell map

The `publish` job runs on `windows-latest`. Every `run` step declares its
shell. Bash-targeted steps (`Verify release tag version`, `Verify immutable
release tag and empty release slot`, `Build Python sidecar binary`, `Build
canonical Findings Pack release payload`, `Sign Findings Pack manifest`,
`Verify generated Findings Pack payload`, `Verify updater signing
prerequisites`, `Check Windows updater artifacts`, `Inventory exact updater
assets before draft creation`, `Create signed release draft`, `Upload exact
updater and Findings Pack assets to draft`, `Verify draft release contents
before promotion`, `Promote verified release draft`, `Verify anonymous latest
release endpoints`, and `Re-draft release after a failed publication check`)
use `shell: bash`; explicit `shell: pwsh` is used for the package install and
Tauri build steps. Heredocs, continuations, assignments, and
`${GITHUB_REF_NAME#v}` therefore run under the intended interpreter rather than
the runner default. The prerequisite, packaging, signing, and artifact-check
commands use the provisioned `uv run --project backend --locked python`
environment. Signing probes and downloaded endpoint fixtures live beneath
`$RUNNER_TEMP`; the updater signing probe has an exit trap that removes both
the probe and detached signature without printing private values.

To exercise only the local updater artifact checker without publishing, use a
native Git Bash session on Windows from a checkout. This fixture uses no
GitHub token, release API, or signing material:

```bash
set -euo pipefail
fixture_root="$(mktemp -d)"
trap 'rm -rf "$fixture_root"' EXIT
bundle_dir="$fixture_root/bundle/nsis"
archive="$bundle_dir/Bhayanak Legends_0.1.12_x64-setup.exe"
signature="$archive.sig"
mkdir -p "$bundle_dir" "$fixture_root/temp"
printf 'fixture installer\n' > "$archive"
printf 'fixture signature\n' > "$signature"
export RUNNER_TEMP="$fixture_root/temp"
export GITHUB_REF_NAME=v0.1.12
export GITHUB_REPOSITORY=theHimanshuShekhar/BhayanakLegends

RUNNER_TEMP_MSYS="$(cygpath -u "$RUNNER_TEMP")"
BUNDLE_DIR_NATIVE="$(cygpath -m "$bundle_dir")"
ARCHIVE_NATIVE="$(cygpath -m "$archive")"
LATEST_JSON_PATH_MSYS="$RUNNER_TEMP_MSYS/latest.json"
LATEST_JSON_PATH_NATIVE="$(cygpath -m "$LATEST_JSON_PATH_MSYS")"
MATCHING_LATEST_PATH_MSYS="$RUNNER_TEMP_MSYS/matching-latest.json"
MATCHING_LATEST_PATH_NATIVE="$(cygpath -m "$MATCHING_LATEST_PATH_MSYS")"
VERSION="${GITHUB_REF_NAME#v}"
uv run --project backend --locked python tools/check_windows_updater_artifacts.py \
  --bundle-dir "$BUNDLE_DIR_NATIVE" \
  --latest-json "$LATEST_JSON_PATH_NATIVE" \
  --write-latest-json \
  --base-url "https://github.com/${GITHUB_REPOSITORY}/releases/download/v${VERSION}" \
  --version "$VERSION"
uv run --project backend --locked python - "$LATEST_JSON_PATH_NATIVE" "$VERSION" "$ARCHIVE_NATIVE" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import quote

path, version, archive = sys.argv[1:]
payload = json.loads(Path(path).read_text(encoding="utf-8"))
assert payload["version"] == version
assert payload["platforms"]["windows-x86_64"]["url"] == (
    "https://github.com/theHimanshuShekhar/BhayanakLegends/releases/download/v"
    + version
    + "/"
    + quote(Path(archive).name)
)
assert "${GITHUB_REF_NAME#v}" not in Path(path).read_text(encoding="utf-8")
PY

cp "$LATEST_JSON_PATH_MSYS" "$MATCHING_LATEST_PATH_MSYS"
rm "$signature"
if uv run --project backend --locked python tools/check_windows_updater_artifacts.py \
  --bundle-dir "$BUNDLE_DIR_NATIVE" --latest-json "$MATCHING_LATEST_PATH_NATIVE"; then
  echo "missing detached signature unexpectedly passed" >&2
  exit 1
fi
printf 'wrong signature\n' > "$signature"
if uv run --project backend --locked python tools/check_windows_updater_artifacts.py \
  --bundle-dir "$BUNDLE_DIR_NATIVE" --latest-json "$MATCHING_LATEST_PATH_NATIVE"; then
  echo "mismatched signature unexpectedly passed" >&2
  exit 1
fi

All commands above stop before Tauri build and all release API creation, asset
upload, or promotion operations; the expected nonzero checks prove the failure
gates without creating or modifying a release.

## Release and tag policy

- `ci.yml` runs the reusable workflow for `main` pushes and pull requests.
- `release.yml` invokes the same workflow for every `v*` tag and checks out
  `${{ github.sha }}` in both verification and publishing jobs. A tag therefore
  cannot bypass the branch checks or verify a different tree.
- The version gate requires the tag to exactly match `package.json`,
  `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock`,
  `backend/pyproject.toml`, `backend/uv.lock`, and the backend runtime
  `APP_VERSION` declaration.
- `publish` has `needs: [verify, packaged-smoke]` and only runs for a tag push
  after both reusable gates succeed. It is the only job that receives
  `GITHUB_TOKEN`, `TAURI_SIGNING_PRIVATE_KEY`, or
  `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.
- The release publisher fails closed if the remote tag does not resolve to
  `${{ github.sha }}` or a release already exists for that tag. It creates a
  draft through the Releases API and captures the returned release ID, uploads
  immutable assets through that ID without replacement, authenticates and
  validates every draft asset by its captured asset ID before promotion,
  performs anonymous `releases/latest/download` endpoint checks only after
  promotion, and re-drafts only the release ID created by this run when a
  post-creation step fails after the pre-mutation promotion-attempt marker is
  written. No post-creation release mutation is addressed by tag.
- All third-party actions are referenced by immutable commit SHA with a version
  comment. Local reusable workflow references are not third-party actions.

## Owner-only history purge procedure

The guarded history purge is a local, owner-authorized procedure. First run
the dry-run inventory against a reviewed mirror and an external identity map:

```sh
python backend/tools/history_purge.py --dry-run \
  --root <mirror> --map-path <external/map> \
  --expected-inventory-count <reviewed> \
  [--backup-dir <external/backup>]
```

The dry run reports paths, fields, and SHA-256 values only, and proves that
refs, objects, and archive snapshots are unchanged. An apply run requires an
external authorization locator:

```sh
python backend/tools/history_purge.py --apply \
  --root <mirror> --map-path <external/map> \
  --backup-dir <external/backup> --backup-reviewed \
  --authorization-comment-id <owner-comment-id>
```

The referenced GitHub comment must be authored by `theHimanshuShekhar` with
owner association and its body must exactly equal:

`AUTHORIZED: rewrite all public BhayanakLegends branches and tags to purge Riot identities and force-push replacements.`

The tool rewrites only the local mirror; it performs at most the documented
bounded authorization-comment read and never contacts origin, force-pushes,
notifies collaborators, publishes releases, or removes caches. Never run apply
or force-push in CI.

After human review, the owner updates origin branch/tag refs, regenerates source
archives/releases, requests GitHub Support cache removal, and notifies
collaborators and fork owners without claiming independent-fork erasure. Make a
fresh clone, run `python tools/check_pii.py --history`, verify original commit
IDs are unreachable and the fixture's non-identity projection is equal, record
evidence, then securely delete the external map.

## Dependency advisory policy

JavaScript uses `pnpm audit --audit-level=high`; Python uses `pip-audit`; Rust
uses `cargo-audit`. High and critical advisories fail verification. Moderate
(or medium) and low advisories are printed and do not fail verification unless
an exception is documented here. The one current Rust exception is
`RUSTSEC-2024-0429` (`glib::VariantStrIter` unsoundness), tracked as a moderate
alert while the dependency upgrade is pending. Unknown or unclassified
severity is actionable and fails closed rather than silently becoming an
exception. The audit jobs themselves fail when their tool cannot produce a
report.

## Non-publishing dry-run checklist

The `workflow_dispatch` inputs are a safe fixture for exercising all three
release states:

1. Run `Release` with `dry_run=true`, `simulate_failure=false`: all gates run,
   and `publish` is skipped because the event is not a tag push (success path).
2. Run `Release` with `dry_run=true`, `simulate_failure=true`: the reusable
   workflow's failure probe is red, and `publish` remains skipped (gate-failure
   path).
3. Push a `v*` tag in a test repository or invoke the release workflow from a
   tag ref: verification runs against that exact SHA, and only a successful
   verification can schedule `publish` (tag-trigger path). Do not provide
   signing secrets in a test repository.

Before merging, validate all workflow YAML files with `actionlint` when
available. If it is unavailable, use a YAML parser and inspect the checklist
above:

```sh
actionlint .github/workflows/*.yml
# fallback:
python3 - <<'PY'
from pathlib import Path
import yaml
for path in Path('.github/workflows').glob('*.yml'):
    yaml.safe_load(path.read_text())
    print(f'valid YAML: {path}')
PY
```

Repository administrators must still configure branch protection to require the
CI workflow, restrict who may create `v*` tags, allow Actions to create
releases, and add the three signing secrets at repository/environment scope.
Those GitHub-side settings cannot be verified from this worktree.

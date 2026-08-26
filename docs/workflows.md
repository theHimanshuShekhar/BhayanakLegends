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
PyInstaller sidecar using the same command as `release.yml`, builds two real
signed NSIS installers (a higher version and the checked-out base version)
with the same `pnpm tauri build --bundles nsis` recipe `release.yml` uses,
installs the lower one under `${{ runner.temp }}`, and launches the installed
executable. It never runs Tauri dev mode and it never receives Riot or
production release credentials; the only signing key involved is generated
fresh for the job.

The job first runs `pnpm tauri signer generate` into `RUNNER_TEMP` to create
a job-local updater keypair, then `tools/patch_updater_endpoint.py` patches
the checked-out config's updater endpoint to the loopback fixture, its
`pubkey` to the paired ephemeral public key, and sets
`dangerousInsecureTransportProtocol` (required for a packaged build to accept
an `http://127.0.0.1` endpoint at all). The same tool's `--set-version` bumps
the config to a higher version for the first signed build and reverts it
before the lower-version build. `tools/patch_updater_endpoint.py --restore`
in an `always()` cleanup step restores the original file byte-for-byte,
removing the endpoint, pubkey, and insecure-transport patches together.

`tools/windows_updater_fixture.py`, bound only to `127.0.0.1`, is started
once the real higher-version archive and its emitted `.sig` exist. Its first
`/latest.json` response offers that real archive with its real signature; once
the archive has been downloaded once, later checks read as up to date at that
same version. When the harness creates an on-disk flip file, checks instead
offer an even higher version whose signature was produced by signing
different bytes with the same ephemeral key — a real artifact, deliberately
non-matching, so any rejection is attributable to signature verification
alone. Every request is recorded path-only.

`tools/windows_packaged_smoke.mjs` connects to the packaged WebView2 through
the runner-local CDP port and asserts the `sidecar_info` command reports an
ephemeral port, `ok`/`degraded` health, and an authenticated token, and that
the initial `/` route renders. In the `update-available` phase it clicks the
existing "Install update" action and rides the download into either the
existing "Restart app" action or the Windows updater plugin's process exit
(the plugin does not pass NSIS's `/R` relaunch flag, so it spawns the
installer and exits the app itself before the JS promise resolves). The
PowerShell harness then waits for that detached installer to finish and
relaunches the app; the `updated` phase asserts the higher version, a
reconnected authenticated sidecar, and a durable Findings Pack. The `invalid`
phase asserts the mismatched-signature offer is rejected with a
signature-verification message and that the sidecar stays healthy; the
harness then asserts the installed executable's version and hash are
byte-for-byte unchanged. The harness tracks pre-existing sidecar PIDs, closes
the app through its window on every graceful phase, and fails if a new
sidecar survives its owner; phase results are written to structured
`smoke-state.json` rather than silently leaving a process behind.

Immediately after the silent install the harness also performs a clean
baseline launch with no `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` set,
records whether the packaged app survives a 12-second probe into
`smoke-state.json`, then stops it — separating "the packaged app is
broken" from "the CDP debug-argument launch breaks it". Every fatal path
additionally prints the app's exit code, the last 40 lines of its
captured stdout/stderr, and any matching Application event-log entries
(faulting module, exception code) from the previous 15 minutes.

On failure, diagnostics are copied through `tools/redact_diagnostics.py` and
uploaded as an artifact. The fixture records paths only; the ephemeral
private key, its password, and the production-config backup live outside the
uploaded diagnostics directory, and the redactor is a second layer that
strips any `tauri signer`-issued key/signature material, PEM blocks,
password/token assignments, and Riot keys wherever they appear in text.
`release.yml` has `publish.needs: [verify, packaged-smoke]`, so a tag cannot
publish unless this packaged gate succeeds.

The Windows runner is required to prove the remaining acceptance criteria:
Linux cannot execute the NSIS installer, WebView2 CDP session, Tauri shell
command, or Windows child-process cleanup. Local verification is limited to
YAML parsing, immutable action-pin checks, Python/Node helper syntax, the
reversible endpoint patch, and the fixture request-state checker. A
successful CI run is the evidence for the packaged install, the signed
relaunch into a genuinely higher version, mismatched-signature rejection, and
owned-sidecar cleanup. Dispatch it directly with
`gh workflow run windows-smoke.yml --ref <branch>` to verify a branch before
it merges.

## Release and tag policy

- `ci.yml` runs the reusable workflow for `main` pushes and pull requests.
- `release.yml` invokes the same workflow for every `v*` tag and checks out
  `${{ github.sha }}` in both verification and publishing jobs. A tag therefore
  cannot bypass the branch checks or verify a different tree.
- `publish` has `needs: [verify, packaged-smoke]` and only runs for a tag push
  after both reusable gates succeed. It is the only job that receives
  `GITHUB_TOKEN`, `TAURI_SIGNING_PRIVATE_KEY`, or
  `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.
- All third-party actions are referenced by immutable commit SHA with a version
  comment. Local reusable workflow references are not third-party actions.

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

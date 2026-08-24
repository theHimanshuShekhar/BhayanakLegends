# Release workflow policy

`.github/workflows/verify.yml` is the reusable required-check workflow. It runs
backend pytest, frontend Vitest, the production frontend build, Playwright
against a sidecar on `127.0.0.1:23110`, and dependency audits. The sidecar uses
`BHAYANAK_TOKEN=dev`; `backend/tools/ci_seed.py` creates deterministic Personal
History only when `data/dev-import/` is absent.

## Packaged Windows smoke

`.github/workflows/windows-smoke.yml` is a reusable, non-publishing gate. It
checks out `${{ github.sha }}` on `windows-latest`, builds the one-file
PyInstaller sidecar using the same command as `release.yml`, builds the NSIS
installer, installs it under `${{ runner.temp }}`, and launches the installed
executable. It never runs Tauri dev mode and it does not receive Riot,
updater-signing, or release credentials.

The smoke starts `tools/windows_updater_fixture.py`, bound only to
`127.0.0.1`. The fixture returns a valid current-version (`0.1.0`) metadata
response on the first updater check, then a local artifact with an intentionally
invalid signature on the second check. `tools/patch_updater_endpoint.py`
temporarily replaces the packaged config endpoint with that loopback URL and
restores the release endpoint in an `always()` cleanup step. Thus updater
assertions cannot contact GitHub or publish a release, while the configured
public key remains the one from `src-tauri/tauri.conf.json`.

`tools/windows_packaged_smoke.mjs` connects to the packaged WebView2 through
the runner-local CDP port and asserts the `sidecar_info` command reports an
ephemeral port and `ok`/`degraded` health, the authenticated sidecar status is
visible, and the initial `/` route renders. It then asserts the valid
no-update state, relaunches the app, installs the fixture update, and checks
that the invalid signature is rejected. The PowerShell harness tracks
pre-existing sidecar PIDs, closes the app through its window, and fails if a
new sidecar survives its owner; startup failures are written to structured
`smoke-state.json` rather than silently leaving a process behind.

On failure, diagnostics are copied through `tools/redact_diagnostics.py` and
uploaded as an artifact. The fixture records paths only; no credentials are
written to the diagnostic directory. `release.yml` has
`publish.needs: [verify, packaged-smoke]`, so a tag cannot publish unless this
packaged gate succeeds.

The Windows runner is required to prove the remaining acceptance criteria:
Linux cannot execute the NSIS installer, WebView2 CDP session, Tauri shell
command, or Windows child-process cleanup. Local verification is limited to
YAML parsing, immutable action-pin checks, Python/Node helper syntax, the
reversible endpoint patch, and the fixture request-state checker. A successful
CI run is the evidence for the packaged install, dynamic handshake/webview
render, updater rejection, and owned-sidecar cleanup.

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

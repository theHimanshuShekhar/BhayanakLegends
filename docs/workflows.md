# Release workflow policy

`.github/workflows/verify.yml` is the reusable required-check workflow. It runs
backend pytest, frontend Vitest, the production frontend build, Playwright
against a sidecar on `127.0.0.1:23110`, and dependency audits. The sidecar uses
`BHAYANAK_TOKEN=dev`; `backend/tools/ci_seed.py` creates deterministic Personal
History only when `data/dev-import/` is absent.

## Release and tag policy

- `ci.yml` runs the reusable workflow for `main` pushes and pull requests.
- `release.yml` invokes the same workflow for every `v*` tag and checks out
  `${{ github.sha }}` in both verification and publishing jobs. A tag therefore
  cannot bypass the branch checks or verify a different tree.
- The `publish` job has `needs: verify` and only runs for a tag push after the
  reusable workflow succeeds. It is the only job that receives
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

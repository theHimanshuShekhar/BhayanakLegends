"""Gate the signed updater release path: config, secrets, and emitted artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "src-tauri" / "tauri.conf.json"
RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _workflow_step(name: str) -> str:
    text = RELEASE.read_text()
    marker = f"      - name: {name}\n"
    start = text.index(marker)
    next_step = text.find("\n      - name:", start + len(marker))
    return text[start:] if next_step == -1 else text[start:next_step]


def test_updater_artifacts_enabled_in_tauri_config():
    config = json.loads(CONFIG.read_text())
    bundle = config["bundle"]
    assert bundle.get("createUpdaterArtifacts") is True
    pubkey = config["plugins"]["updater"]["pubkey"]
    assert isinstance(pubkey, str) and len(pubkey) > 100


def test_windows_bash_steps_declare_their_shell_and_runner_paths():
    bash_steps = (
        "Verify updater signing prerequisites",
        "Check Windows updater artifacts",
        "Verify emitted updater artifacts",
    )
    for name in bash_steps:
        step = _workflow_step(name)
        assert re.search(r"^        shell: bash$", step, re.MULTILINE)

    checker = _workflow_step("Check Windows updater artifacts")
    assert 'LATEST_JSON="$RUNNER_TEMP/latest.json"' in checker
    assert 'VERSION="${GITHUB_REF_NAME#v}"' in checker
    assert '--version "$VERSION"' in checker

    emitted = _workflow_step("Verify emitted updater artifacts")
    assert 'ASSETS_FILE="$RUNNER_TEMP/assets.txt"' in emitted
    assert 'TAG="v${VERSION}"' in emitted


def test_release_job_requires_signing_secret_and_prerequisites():
    text = RELEASE.read_text()
    assert "Verify updater signing prerequisites" in text, (
        "release must fail closed before publishing when signing prerequisites are missing"
    )
    assert "TAURI_SIGNING_PRIVATE_KEY" in text
    assert "createUpdaterArtifacts" in text
    prerequisites = _workflow_step("Verify updater signing prerequisites")
    assert "uv run --project backend --locked python - <<'PY'" in prerequisites
    assert "python3 -" not in prerequisites


def test_release_job_verifies_emitted_updater_artifacts_after_publish():
    text = RELEASE.read_text()
    assert "Verify emitted updater artifacts" in text, (
        "release must verify emitted updater artifacts after the build"
    )
    post_index = text.index("Verify emitted updater artifacts")
    tail = text[post_index:]
    assert "latest.json" in tail and ".sig" in tail

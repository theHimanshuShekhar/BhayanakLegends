"""Gate the signed updater release path: config, secrets, and emitted artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "src-tauri" / "tauri.conf.json"
RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_updater_artifacts_enabled_in_tauri_config():
    config = json.loads(CONFIG.read_text())
    bundle = config["bundle"]
    assert bundle.get("createUpdaterArtifacts") is True
    pubkey = config["plugins"]["updater"]["pubkey"]
    assert isinstance(pubkey, str) and len(pubkey) > 100


def test_release_job_requires_signing_secret_and_prerequisites():
    text = RELEASE.read_text()
    assert "Verify updater signing prerequisites" in text, (
        "release must fail closed before publishing when signing prerequisites are missing"
    )
    assert "TAURI_SIGNING_PRIVATE_KEY" in text
    assert "createUpdaterArtifacts" in text


def test_release_job_verifies_emitted_updater_artifacts_after_publish():
    text = RELEASE.read_text()
    assert "Verify emitted updater artifacts" in text, (
        "release must verify emitted updater artifacts after the build"
    )
    post_index = text.index("Verify emitted updater artifacts")
    tail = text[post_index:]
    assert "latest.json" in tail and ".sig" in tail

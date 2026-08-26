"""Contract tests for signed Windows updater artifact publication."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "check_windows_updater_artifacts.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_windows_updater_artifacts", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolves __module__ via sys.modules
    spec.loader.exec_module(module)
    return module


def make_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    bundle = tmp_path / "bundle" / "nsis"
    bundle.mkdir(parents=True)
    archive = bundle / "Bhayanak Legends_0.1.0_x64-setup.exe"
    archive.write_bytes(b"signed installer bytes")
    signature = archive.with_name(archive.name + ".sig")
    signature_text = "detached-signature-content"
    signature.write_text(signature_text, encoding="utf-8")
    metadata = tmp_path / "latest.json"
    metadata.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "platforms": {
                    "windows-x86_64": {
                        "signature": signature_text,
                        "url": "https://github.example/releases/download/v0.1.0/"
                        + quote(archive.name),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return bundle, metadata, archive, signature_text


def test_matching_windows_artifacts_pass(tmp_path: Path):
    checker = load_checker()
    bundle, metadata, archive, _ = make_fixture(tmp_path)

    inventory = checker.check_artifacts(bundle, metadata)

    assert inventory.archive == archive
    assert inventory.signature == archive.with_name(archive.name + ".sig")


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        ("archive", "archive"),
        ("signature_file", "signature"),
        ("signature_bytes", "signature"),
        ("platform", "windows-x86_64"),
        ("url", "URL"),
        ("metadata_signature", "signature"),
    ],
)
def test_invalid_windows_artifacts_fail_before_publication(
    tmp_path: Path, mutation: str, diagnostic: str
):
    checker = load_checker()
    bundle, metadata, archive, _ = make_fixture(tmp_path)
    latest = json.loads(metadata.read_text(encoding="utf-8"))

    if mutation == "archive":
        archive.unlink()
    elif mutation == "signature_file":
        archive.with_name(archive.name + ".sig").unlink()
    elif mutation == "signature_bytes":
        archive.with_name(archive.name + ".sig").write_bytes(b"not-utf8-\xff")
    elif mutation == "platform":
        latest["platforms"] = {}
        metadata.write_text(json.dumps(latest), encoding="utf-8")
    elif mutation == "url":
        latest["platforms"]["windows-x86_64"]["url"] = "https://example.invalid/other.exe"
        metadata.write_text(json.dumps(latest), encoding="utf-8")
    elif mutation == "metadata_signature":
        latest["platforms"]["windows-x86_64"]["signature"] = "wrong-signature"
        metadata.write_text(json.dumps(latest), encoding="utf-8")

    with pytest.raises(checker.ArtifactCheckError, match=diagnostic):
        checker.check_artifacts(bundle, metadata)


def test_release_workflow_checks_generated_inventory_before_publishing():
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    build = workflow.index("pnpm tauri build --bundles nsis")
    check = workflow.index("check_windows_updater_artifacts.py")
    publish = workflow.index("tauri-apps/tauri-action@")

    assert build < check < publish
    assert "--write-latest-json" in workflow
    assert "includeUpdaterJson: true" in workflow
    assert "updaterJsonPreferNsis: true" in workflow

    smoke = (REPO_ROOT / ".github/workflows/windows-smoke.yml").read_text(encoding="utf-8")
    assert "tauri-apps/tauri-action@" not in smoke


def test_tauri_config_enables_signed_updater_artifacts():
    config = json.loads((REPO_ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))

    assert config["bundle"]["createUpdaterArtifacts"] is True
    assert config["plugins"]["updater"]["endpoints"] == [
        "https://github.com/theHimanshuShekhar/BhayanakLegends/releases/latest/download/latest.json"
    ]
    assert config["plugins"]["updater"]["pubkey"]

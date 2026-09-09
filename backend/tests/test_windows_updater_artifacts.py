"""Contract tests for signed Windows updater artifact publication."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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

def test_checker_command_emits_versioned_metadata_and_rejects_bad_inventory(
    tmp_path: Path,
):
    bundle, _, archive, _ = make_fixture(tmp_path)
    generated = tmp_path / "generated-latest.json"
    command = [
        sys.executable,
        str(TOOL_PATH),
        "--bundle-dir",
        str(bundle),
        "--latest-json",
        str(generated),
        "--write-latest-json",
        "--base-url",
        "https://github.example/releases/download/v1.2.3",
        "--version",
        "1.2.3",
    ]

    result = subprocess.run(command, capture_output=True, text=True, check=False)

    assert result.returncode == 0
    payload = json.loads(generated.read_text(encoding="utf-8"))
    platform = payload["platforms"]["windows-x86_64"]
    assert payload["version"] == "1.2.3"
    assert platform["url"] == (
        "https://github.example/releases/download/v1.2.3/" + quote(archive.name)
    )
    assert platform["signature"] == "detached-signature-content"

    archive.with_name(archive.name + ".sig").write_text("wrong", encoding="utf-8")
    mismatch = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--bundle-dir",
            str(bundle),
            "--latest-json",
            str(generated),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert mismatch.returncode != 0
    assert "signature" in mismatch.stderr

    archive.unlink()
    missing = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--bundle-dir",
            str(bundle),
            "--latest-json",
            str(generated),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    assert "archive" in missing.stderr


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


def test_release_workflow_stages_safe_updater_names_before_id_addressed_upload():
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    build = workflow.index("pnpm tauri build --bundles nsis")
    stage = workflow.index("Stage canonical Windows updater assets")
    check = workflow.index("check_windows_updater_artifacts.py")
    draft = workflow.index('releases" > "$CREATE_RESPONSE"')
    upload = workflow.index('url = "${UPLOAD_URL}?name=${asset_name}"')
    upload_start = workflow.index("Upload exact updater and Findings Pack assets to draft")
    verify_start = workflow.index("Verify draft release contents before promotion")
    upload_step = workflow[upload_start:verify_start]

    assert build < stage < check < draft < upload
    assert "--write-latest-json" in workflow
    assert "release-inventory.json" in workflow
    assert "release-create-response.json" in workflow
    assert '--field "draft=true"' in workflow
    assert "target_commitish" in workflow
    assert "upload_url" in workflow
    assert "uploads.github.com" in workflow
    assert "{?name,label}" in workflow
    assert "gh api" in workflow
    assert "releases/${RELEASE_ID}/assets" in workflow
    assert "releases/assets/${asset_id}" in workflow
    assert "--config -" in upload_step
    assert 'Authorization: Bearer ${GH_TOKEN}' in upload_step
    assert 'ASSET_PATH_CURL="$(cygpath -m "$asset_path")"' in upload_step
    assert 'data-binary = "@${ASSET_PATH_CURL}"' in upload_step
    assert 'data-binary = "@${asset_path}"' not in upload_step
    assert '--input "$asset_path"' not in upload_step
    assert "--method POST" not in upload_step
    assert 'releases/${RELEASE_ID}/assets?name=${asset_name}' not in upload_step
    assert "--clobber" not in workflow
    assert "gh release create" not in workflow
    assert "gh release upload" not in workflow
    assert "gh release download" not in workflow
    assert "gh release edit" not in workflow
    assert "tauri-apps/tauri-action@" not in workflow

    smoke = (REPO_ROOT / ".github/workflows/windows-smoke.yml").read_text(encoding="utf-8")
    assert "tauri-apps/tauri-action@" not in smoke


def test_release_staged_updater_names_preserve_local_bytes():
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'bhayanak-legends-{version}-setup.exe' in workflow
    assert 'bhayanak-legends-{version}-windows-x86_64.nsis.zip' in workflow
    assert 'staged_dir / f"bhayanak-legends-{version}-windows-x86_64.nsis.zip.sig"' in workflow
    assert 'filecmp.cmp(source, target, shallow=False)' in workflow
    assert 'shutil.copyfile(source, target)' in workflow
    assert "release asset name is not GitHub-safe" in workflow

def test_tauri_config_enables_signed_updater_artifacts():
    config = json.loads((REPO_ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))

    assert config["bundle"]["createUpdaterArtifacts"] is True
    assert config["plugins"]["updater"]["endpoints"] == [
        "https://github.com/theHimanshuShekhar/BhayanakLegends/releases/latest/download/latest.json"
    ]
    assert config["plugins"]["updater"]["pubkey"]

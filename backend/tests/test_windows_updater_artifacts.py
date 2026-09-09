"""Contract tests for signed Windows updater artifact publication."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
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
    archive = bundle / "Bhayanak Legends_0.1.9_x64-setup.exe"
    archive.write_bytes(b"signed installer bytes")
    signature = archive.with_name(archive.name + ".sig")
    signature_text = "detached-signature-content"
    signature.write_text(signature_text, encoding="utf-8")
    metadata = tmp_path / "latest.json"
    metadata.write_text(
        json.dumps(
            {
                "version": "0.1.9",
                "platforms": {
                    "windows-x86_64": {
                        "signature": signature_text,
                        "url": "https://github.example/releases/download/v0.1.9/"
                        + quote(archive.name),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return bundle, metadata, archive, signature_text


def _workflow_python(step_name: str, marker: str = "          import ") -> str:
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    step_start = workflow.index(f"      - name: {step_name}")
    source_start = workflow.index(marker, step_start)
    source_end = workflow.index("          PY", source_start)
    return textwrap.dedent(workflow[source_start:source_end])


def _workflow_shell(step_name: str) -> str:
    lines = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8").splitlines()
    step_start = lines.index(f"      - name: {step_name}")
    run_start = next(
        index for index in range(step_start, len(lines)) if lines[index] == "        run: |"
    )
    step_end = next(
        (
            index
            for index in range(run_start + 1, len(lines))
            if lines[index].startswith("      - name: ")
        ),
        len(lines),
    )
    return textwrap.dedent("\n".join(lines[run_start + 1 : step_end]))


def _run_workflow_shell(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_workflow_python(script: str, *args: Path | str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script, *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_latest(
    path: Path, version: str, updater_name: str, signature_text: str
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": version,
                "platforms": {
                    "windows-x86_64": {
                        "signature": signature_text,
                        "url": "https://github.example/releases/download/v"
                        + version
                        + "/"
                        + quote(updater_name),
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _stage_and_inventory(
    tmp_path: Path,
    source_files: dict[str, bytes],
    version: str,
    updater_name: str,
    signature_text: str,
) -> tuple[Path, dict[str, object]]:
    source_dir = tmp_path / "source"
    staged_dir = tmp_path / "staged"
    source_dir.mkdir()
    staged_dir.mkdir()
    for name, content in source_files.items():
        (source_dir / name).write_bytes(content)

    staged = _run_workflow_python(
        _workflow_python("Stage canonical Windows updater assets", "          import filecmp"),
        source_dir,
        staged_dir,
        version,
    )
    assert staged.returncode == 0, staged.stderr

    latest_path = tmp_path / "latest.json"
    _write_latest(latest_path, version, updater_name, signature_text)
    inventory_path = tmp_path / "release-inventory.json"
    inventory = _run_workflow_python(
        _workflow_python("Inventory exact updater assets before draft creation"),
        inventory_path,
        latest_path,
        staged_dir,
        f"v{version}",
    )
    assert inventory.returncode == 0, inventory.stderr
    return staged_dir, json.loads(inventory_path.read_text(encoding="utf-8"))


def _assert_upload_selection_is_unique(
    inventory_path: Path, expected_assets: list[str]
) -> None:
    selected = _run_workflow_python(
        _workflow_python("Upload exact updater and Findings Pack assets to draft"),
        inventory_path,
    )
    assert selected.returncode == 0, selected.stderr
    assert selected.stdout.splitlines() == expected_assets
    assert len(selected.stdout.splitlines()) == len(set(selected.stdout.splitlines()))

def test_upload_path_checks_normalize_windows_runner_temp(tmp_path: Path):
    version = "0.1.9"
    repository = "theHimanshuShekhar/BhayanakLegends"
    native_temp = r"D:\a\_temp"
    runner_temp = tmp_path / "runner-temp"
    bundle_dir = runner_temp / "updater-bundle"
    bundle_dir.mkdir(parents=True)
    updater_assets = [
        f"bhayanak-legends-{version}-windows-x86_64-setup.exe",
        f"bhayanak-legends-{version}-windows-x86_64-setup.exe.sig",
    ]
    other_assets = [
        "latest.json",
        "findings-pack.v2.zip",
        "findings-pack-manifest.json",
        "findings-pack-manifest.json.sig",
    ]
    for asset_name in updater_assets:
        (bundle_dir / asset_name).write_bytes(b"updater asset")
    for asset_name in other_assets:
        (runner_temp / asset_name).write_bytes(b"release asset")
    (runner_temp / "release-inventory.json").write_text(
        json.dumps({"assets": updater_assets}) + "\n",
        encoding="utf-8",
    )
    (runner_temp / "release-identity").write_text(
        f"v{version}\n123\nhttps://uploads.github.com/repos/{repository}/releases/123/assets\n",
        encoding="utf-8",
    )
    (runner_temp / "release-promotion-attempt").write_text(
        f"v{version}\n123\n",
        encoding="utf-8",
    )
    (runner_temp / "release-promotion-marker").write_text(
        f"v{version}\n123\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    cygpath = fake_bin / "cygpath"
    cygpath.write_text(
        """#!/usr/bin/env python3
import os
import sys

mode, path = sys.argv[1:3]
native_root = r"D:\\a\\_temp"
posix_root = os.environ["FAKE_POSIX_ROOT"]
if mode == "-u":
    if path.startswith(native_root):
        suffix = path[len(native_root) :]
        print(posix_root + suffix.replace("\\\\", "/"))
    else:
        print(path)
elif mode == "-m":
    suffix = path[len(posix_root) :] if path.startswith(posix_root) else path
    print("D:/a/_temp" + suffix.replace("\\\\", "/"))
else:
    raise SystemExit(f"unsupported cygpath mode: {mode}")
""",
        encoding="utf-8",
    )
    cygpath.chmod(0o755)
    gh = fake_bin / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"@tsv"* ]]; then
  printf '123\\t%s\\ttrue\\n' "$GITHUB_REF_NAME"
fi
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    uv = fake_bin / "uv"
    uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$UV_ARGS_LOG"
printf '%s\n' "$FAKE_UPDATER_ASSETS"
""",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    curl_log = tmp_path / "curl-config.log"
    uv_args_log = tmp_path / "uv-args.log"
    curl = fake_bin / "curl"
    curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
cat >> "$CURL_LOG"
printf '\\n---\\n' >> "$CURL_LOG"
""",
        encoding="utf-8",
    )
    curl.chmod(0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
            "GH_TOKEN": "test-token",
            "RUNNER_TEMP": native_temp,
            "INVENTORY_PATH": native_temp + r"\release-inventory.json",
            "GITHUB_REF_NAME": f"v{version}",
            "GITHUB_REPOSITORY": repository,
            "FAKE_POSIX_ROOT": str(runner_temp),
            "FAKE_UPDATER_ASSETS": "\n".join(updater_assets),
            "CURL_LOG": str(curl_log),
            "UV_ARGS_LOG": str(uv_args_log),
        }
    )
    result = _run_workflow_shell(
        _workflow_shell("Upload exact updater and Findings Pack assets to draft"),
        environment,
    )

    assert result.returncode == 0, result.stderr
    configs = curl_log.read_text(encoding="utf-8").split("\n---\n")
    assert len(configs) == len(updater_assets) + len(other_assets) + 1
    assert all('data-binary = "@D:/a/_temp/' in config for config in configs[:-1])
    expected_upload_targets = {
        f'data-binary = "@D:/a/_temp/updater-bundle/{name}"' for name in updater_assets
    } | {f'data-binary = "@D:/a/_temp/{name}"' for name in other_assets}
    observed_upload_targets = {
        line.strip()
        for config in configs[:-1]
        for line in config.splitlines()
        if line.startswith("data-binary = ")
    }
    assert observed_upload_targets == expected_upload_targets
    uv_args = uv_args_log.read_text(encoding="utf-8").splitlines()
    assert any("D:/a/_temp/release-inventory.json" in line for line in uv_args)
    for step_name, stop_marker in (
        (
            "Verify draft release contents before promotion",
            'RELEASE_JSON="$RUNNER_TEMP_MSYS/release-before-verification.json"',
        ),
        ("Promote verified release draft", "RELEASE_STATE="),
        (
            "Verify anonymous latest release endpoints",
            'download_anonymous "$PUBLIC_BASE/latest.json" "$PUBLIC_DIR_NATIVE/latest.json"',
        ),
        ("Re-draft release after a failed publication check", "EXPECTED_TAG="),
    ):
        script = _workflow_shell(step_name)
        probe = script[: script.index(stop_marker)] + 'printf "%s\\n" "$RUNNER_TEMP_MSYS"\n'
        probe_result = _run_workflow_shell(probe, environment)
        assert probe_result.returncode == 0, f"{step_name}: {probe_result.stderr}"
        assert probe_result.stdout.strip() == str(runner_temp)


def test_workflow_stages_signed_exe_once_and_uploads_unique_assets(tmp_path: Path):
    version = "0.1.9"
    source_name = "Bhayanak Legends_0.1.9_x64-setup.exe"
    signature_text = "signed-exe-signature"
    staged_dir, inventory = _stage_and_inventory(
        tmp_path,
        {
            source_name: b"signed installer bytes",
            source_name + ".sig": signature_text.encode(),
        },
        version,
        f"bhayanak-legends-{version}-windows-x86_64-setup.exe",
        signature_text,
    )

    canonical = f"bhayanak-legends-{version}-windows-x86_64-setup.exe"
    expected_assets = [canonical, canonical + ".sig"]
    assert {path.name for path in staged_dir.iterdir()} == set(expected_assets)
    assert inventory["installer"] == canonical
    assert inventory["updater"] == canonical
    assert inventory["signature"] == canonical + ".sig"
    assert inventory["assets"] == expected_assets
    _assert_upload_selection_is_unique(
        tmp_path / "release-inventory.json", expected_assets
    )


def test_workflow_stages_separate_unsigned_installer_and_signed_archive(
    tmp_path: Path,
):
    version = "0.1.9"
    installer_name = "Bhayanak Legends_0.1.9_x64-setup.exe"
    archive_name = "Bhayanak Legends_0.1.9_x64.nsis.zip"
    signature_text = "signed-archive-signature"
    staged_dir, inventory = _stage_and_inventory(
        tmp_path,
        {
            installer_name: b"unsigned installer bytes",
            archive_name: b"signed updater bytes",
            archive_name + ".sig": signature_text.encode(),
        },
        version,
        f"bhayanak-legends-{version}-windows-x86_64.nsis.zip",
        signature_text,
    )

    canonical_installer = f"bhayanak-legends-{version}-setup.exe"
    canonical_archive = f"bhayanak-legends-{version}-windows-x86_64.nsis.zip"
    expected_assets = [
        canonical_installer,
        canonical_archive,
        canonical_archive + ".sig",
    ]
    assert {path.name for path in staged_dir.iterdir()} == set(expected_assets)
    assert inventory["installer"] == canonical_installer
    assert inventory["updater"] == canonical_archive
    assert inventory["signature"] == canonical_archive + ".sig"
    assert inventory["assets"] == expected_assets
    _assert_upload_selection_is_unique(
        tmp_path / "release-inventory.json", expected_assets
    )


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
    draft = workflow.index('releases" > "$CREATE_RESPONSE_MSYS"')
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
    assert "exactly one signed updater candidate" in workflow
    assert "dict.fromkeys" in workflow
    assert '"assets": asset_names' in workflow
    assert "gh api" in upload_step
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
    assert "len(set(assets)) != len(assets)" in upload_step
    assert "--clobber" not in workflow
    assert "gh release create" not in workflow
    assert "gh release upload" not in workflow
    assert "gh release download" not in workflow
    assert "gh release edit" not in workflow
    assert "tauri-apps/tauri-action@" not in workflow

def test_release_staged_updater_names_preserve_local_bytes():
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'bhayanak-legends-{version}-setup.exe' in workflow
    assert 'bhayanak-legends-{version}-windows-x86_64-setup.exe' in workflow
    assert 'bhayanak-legends-{version}-windows-x86_64.nsis.zip' in workflow
    assert 'canonical_updater.with_name(canonical_updater.name + ".sig")' in workflow
    assert "if updater == installer" in workflow
    assert "signed_updaters" in workflow
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

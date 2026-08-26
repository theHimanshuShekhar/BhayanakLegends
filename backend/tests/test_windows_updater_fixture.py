"""Subprocess-level tests for the loopback Windows updater fixture.

The fixture must serve the real higher-version updater archive with its
emitted signature on the first metadata check, flip to a same-version quiet
response once that archive has been downloaded, and flip to a rejected
higher-version offer whose signature does not match the served bytes once the
harness creates the flip file. No fake artifact may ever be mistaken for a
valid update, and every request is recorded as a path-only diagnostic row.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tools" / "windows_updater_fixture.py"


def http_get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.fixture
def pack_root(tmp_path: Path) -> Path:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "findings-pack.v1.json").write_text(
        json.dumps({"schema_version": 1, "pack_version": "v1", "findings": []}), encoding="utf-8"
    )
    (root / "pack.schema.json").write_text(json.dumps({"type": "object"}), encoding="utf-8")
    return root


@pytest.fixture
def artifacts(tmp_path: Path) -> dict[str, Path]:
    # tauri signer writes keys/signatures as a single line of base64 text
    # (base64 of the minisign armored comment+key block); the fixture must
    # copy that text verbatim into latest.json rather than re-encoding it.
    artifact = tmp_path / "BhayanakLegends_0.2.0_x64-setup.nsis.zip"
    artifact.write_bytes(b"real-higher-version-updater-archive-bytes")
    signature = tmp_path / "BhayanakLegends_0.2.0_x64-setup.nsis.zip.sig"
    signature.write_text("dW50cnVzdGVkIGNvbW1lbnQ6VkFMSURfU0lHTkFUVVJFX0RBVEE=", encoding="utf-8")
    rejected_signature = tmp_path / "rejected.sig"
    rejected_signature.write_text("dW50cnVzdGVkIGNvbW1lbnQ6TUlTTUFUQ0hFRF9TSUdOQVRVUkU=", encoding="utf-8")
    return {"artifact": artifact, "signature": signature, "rejected_signature": rejected_signature}


def start_fixture(
    tmp_path: Path,
    pack_root: Path,
    artifacts: dict[str, Path],
    *,
    update_version: str = "0.2.0",
    rejected_version: str = "0.3.0",
    extra_args: list[str] | None = None,
) -> subprocess.Popen[str]:
    state_file = tmp_path / "state.json"
    flip_file = tmp_path / "flip"
    command = [
        sys.executable,
        str(FIXTURE),
        "--state-file",
        str(state_file),
        "--port",
        "0",
        "--update-version",
        update_version,
        "--rejected-version",
        rejected_version,
        "--artifact",
        str(artifacts["artifact"]),
        "--signature",
        str(artifacts["signature"]),
        "--rejected-signature",
        str(artifacts["rejected_signature"]),
        "--flip-file",
        str(flip_file),
        "--pack-root",
        str(pack_root),
    ]
    command.extend(extra_args or [])
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait_for_state(proc: subprocess.Popen[str], state_file: Path) -> dict[str, object]:
    deadline = time.time() + 10
    while time.time() < deadline:
        if state_file.exists():
            return json.loads(state_file.read_text(encoding="utf-8"))
        if proc.poll() is not None:
            raise AssertionError(f"fixture exited before starting: {proc.stderr.read()}")
        time.sleep(0.02)
    raise AssertionError("fixture did not write its state file in time")


def stop_fixture(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture
def running_fixture(tmp_path, pack_root, artifacts):
    state_file = tmp_path / "state.json"
    flip_file = tmp_path / "flip"
    proc = start_fixture(tmp_path, pack_root, artifacts)
    try:
        state = wait_for_state(proc, state_file)
        base = f"http://{state['host']}:{state['port']}"
        yield {"base": base, "state": state, "flip_file": flip_file, "requests_file": Path(state["requests_file"])}
    finally:
        stop_fixture(proc)


def test_first_check_offers_the_real_higher_version_with_matching_signature(running_fixture, artifacts):
    base = running_fixture["base"]
    status, body = http_get(f"{base}/latest.json")
    assert status == 200
    payload = json.loads(body)
    assert payload["version"] == "0.2.0"
    platform = payload["platforms"]["windows-x86_64"]
    assert platform["url"] == f"{base}/updater/update.bin"
    expected_signature = artifacts["signature"].read_text(encoding="utf-8").strip()
    assert platform["signature"] == expected_signature


def test_valid_artifact_download_returns_exact_archive_bytes(running_fixture, artifacts):
    status, body = http_get(f"{running_fixture['base']}/updater/update.bin")
    assert status == 200
    assert body == artifacts["artifact"].read_bytes()


def test_check_after_valid_download_is_same_version_quiet(running_fixture):
    base = running_fixture["base"]
    http_get(f"{base}/latest.json")
    http_get(f"{base}/updater/update.bin")  # consume the valid artifact once
    status, body = http_get(f"{base}/latest.json")
    assert status == 200
    payload = json.loads(body)
    assert payload["version"] == "0.2.0", "installed (updated) version must read as current, not available"


def test_repeated_checks_before_download_keep_offering_the_valid_update(running_fixture):
    base = running_fixture["base"]
    first = json.loads(http_get(f"{base}/latest.json")[1])
    second = json.loads(http_get(f"{base}/latest.json")[1])
    assert first["version"] == second["version"] == "0.2.0"
    assert first["platforms"]["windows-x86_64"]["url"] == f"{base}/updater/update.bin"


def test_flip_file_switches_to_rejected_offer_with_mismatched_signature(running_fixture, artifacts):
    base = running_fixture["base"]
    http_get(f"{base}/latest.json")
    http_get(f"{base}/updater/update.bin")
    running_fixture["flip_file"].write_text("invalid-phase", encoding="utf-8")

    status, body = http_get(f"{base}/latest.json")
    assert status == 200
    payload = json.loads(body)
    assert payload["version"] == "0.3.0"
    platform = payload["platforms"]["windows-x86_64"]
    assert platform["url"] == f"{base}/updater/rejected.bin"
    rejected_signature = artifacts["rejected_signature"].read_text(encoding="utf-8").strip()
    assert platform["signature"] == rejected_signature
    valid_signature = artifacts["signature"].read_text(encoding="utf-8").strip()
    assert platform["signature"] != valid_signature


def test_rejected_artifact_serves_the_same_bytes_as_the_valid_one(running_fixture, artifacts):
    base = running_fixture["base"]
    running_fixture["flip_file"].write_text("invalid-phase", encoding="utf-8")
    status, body = http_get(f"{base}/updater/rejected.bin")
    assert status == 200
    assert body == artifacts["artifact"].read_bytes(), "rejection must be attributable to the signature alone"


def test_pack_manifest_and_asset_are_still_served(running_fixture):
    base = running_fixture["base"]
    status, body = http_get(f"{base}/findings-pack-manifest.json")
    assert status == 200
    manifest = json.loads(body)
    assert manifest["pack_version"] == "v2-smoke"
    assert manifest["download_url"] == f"{base}/findings-pack.zip"

    status, zip_body = http_get(manifest["download_url"])
    assert status == 200
    assert len(zip_body) == manifest["size"]


def test_unknown_path_returns_404(running_fixture):
    status, _body = http_get(f"{running_fixture['base']}/nope")
    assert status == 404


def test_requests_are_recorded_path_only_with_no_query_or_host(running_fixture):
    base = running_fixture["base"]
    http_get(f"{base}/latest.json?token=leak")
    http_get(f"{base}/findings-pack-manifest.json")

    rows = [json.loads(line) for line in running_fixture["requests_file"].read_text(encoding="utf-8").splitlines()]
    assert rows, "expected at least one recorded request"
    for row in rows:
        assert set(row) == {"method", "path"}
        assert row["method"] == "GET"
        assert "?" not in row["path"]
        assert "token" not in row["path"]
        assert "://" not in row["path"]
    assert {"/latest.json", "/findings-pack-manifest.json"} <= {row["path"] for row in rows}


def test_missing_artifact_file_exits_nonzero_before_binding(tmp_path, pack_root, artifacts):
    missing = tmp_path / "does-not-exist.zip"
    proc = start_fixture(
        tmp_path,
        pack_root,
        {**artifacts, "artifact": missing},
    )
    try:
        stdout, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    assert proc.returncode != 0
    assert not (tmp_path / "state.json").exists()
    assert "updater artifact" in stderr


def test_empty_signature_file_exits_nonzero(tmp_path, pack_root, artifacts):
    artifacts["signature"].write_text("", encoding="utf-8")
    proc = start_fixture(tmp_path, pack_root, artifacts)
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode != 0
    assert "empty" in stderr


def test_rejected_signature_equal_to_valid_signature_is_rejected_at_startup(tmp_path, pack_root, artifacts):
    artifacts["rejected_signature"].write_text(artifacts["signature"].read_text(encoding="utf-8"), encoding="utf-8")
    proc = start_fixture(tmp_path, pack_root, artifacts)
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode != 0
    assert "differ" in stderr


def test_equal_update_and_rejected_versions_are_rejected_at_startup(tmp_path, pack_root, artifacts):
    proc = start_fixture(tmp_path, pack_root, artifacts, update_version="0.2.0", rejected_version="0.2.0")
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode != 0
    assert "differ" in stderr

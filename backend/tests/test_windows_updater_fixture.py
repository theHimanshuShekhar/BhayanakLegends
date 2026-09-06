"""Subprocess-level regression tests for the real Windows updater fixture."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tools" / "windows_updater_fixture.py"


def _wait_for_state(path: Path, process: subprocess.Popen[str]) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise AssertionError(
                f"fixture exited before writing state: {process.stderr.read()}"
            )
        time.sleep(0.05)
    raise AssertionError("fixture did not write its state file")


@pytest.fixture
def fixture_server(tmp_path: Path):
    state_path = tmp_path / "fixture.json"
    valid_artifact = tmp_path / "valid.nsis.zip"
    valid_signature = tmp_path / "valid.nsis.zip.sig"
    invalid_artifact = tmp_path / "invalid.nsis.zip"
    invalid_signature = tmp_path / "invalid.nsis.zip.sig"
    valid_bytes = b"real emitted signed updater bytes"
    invalid_bytes = b"tampered updater bytes"
    signature = "valid-detached-signature\n"
    valid_artifact.write_bytes(valid_bytes)
    valid_signature.write_text(signature, encoding="utf-8")
    invalid_artifact.write_bytes(invalid_bytes)
    # Deliberately reuse the valid signature for different bytes.
    invalid_signature.write_text(signature, encoding="utf-8")

    process = subprocess.Popen(
        [
            sys.executable,
            str(FIXTURE),
            "--state-file",
            str(state_path),
            "--port",
            "0",
            "--current-version",
            "0.1.0",
            "--valid-version",
            "0.1.1",
            "--valid-artifact",
            str(valid_artifact),
            "--valid-signature",
            str(valid_signature),
            "--invalid-version",
            "0.1.2",
            "--invalid-artifact",
            str(invalid_artifact),
            "--invalid-signature",
            str(invalid_signature),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        state = _wait_for_state(state_path, process)
        yield process, state, valid_bytes, invalid_bytes
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _get(port: int, path: str, *, headers: dict[str, str] | None = None) -> bytes:
    request = Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    with urlopen(request, timeout=5) as response:
        return response.read()


def test_fixture_serves_exact_valid_then_mismatched_artifacts(fixture_server) -> None:
    _process, state, valid_bytes, invalid_bytes = fixture_server
    port = int(state["port"])

    first = json.loads(_get(port, "/latest.json"))
    first_platform = first["platforms"]["windows-x86_64"]
    assert first["version"] == "0.1.1"
    assert _get(port, str(first_platform["url"]).split(f"127.0.0.1:{port}", 1)[1]) == valid_bytes

    second = json.loads(_get(port, "/latest.json"))
    second_platform = second["platforms"]["windows-x86_64"]
    assert second["version"] == "0.1.2"
    assert _get(port, str(second_platform["url"]).split(f"127.0.0.1:{port}", 1)[1]) == invalid_bytes
    assert first_platform["signature"] == second_platform["signature"]
    manifest = json.loads(_get(port, "/findings-pack-manifest.json"))
    packed = _get(port, "/findings-pack.zip")
    assert manifest["pack_version"] == state["pack_version"]
    assert manifest["size"] == len(packed) == state["pack_size"]
    assert manifest["sha256"] == hashlib.sha256(packed).hexdigest() == state["pack_sha256"]
    assert manifest["required_model_artifacts"] == state["required_model_artifacts"]
    pack_root = REPO_ROOT / "pack"
    expected_files = sorted(
        path.relative_to(pack_root).as_posix()
        for path in pack_root.rglob("*")
        if path.is_file()
    )
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        assert archive.namelist() == expected_files
        assert {
            name: archive.read(name)
            for name in expected_files
        } == {
            name: (pack_root / name).read_bytes()
            for name in expected_files
        }


    requests = Path(str(state["requests_file"])).read_text(encoding="utf-8")
    assert '"path": "/latest.json"' in requests
    assert "/artifacts/valid/valid.nsis.zip" in requests
    assert "/artifacts/invalid/invalid.nsis.zip" in requests
    assert "127.0.0.1" not in requests
    assert "?" not in requests


def test_fixture_rejects_non_loopback_and_query_requests(fixture_server) -> None:
    process, state, _valid_bytes, _invalid_bytes = fixture_server
    port = int(state["port"])

    with pytest.raises(HTTPError) as query_error:
        _get(port, "/latest.json?token=should-not-be-recorded")
    assert query_error.value.code == 400

    request = Request(
        f"http://127.0.0.1:{port}/latest.json",
        headers={"Host": "localhost"},
    )
    with pytest.raises(HTTPError) as host_error:
        with urlopen(request, timeout=5):
            pass
    assert host_error.value.code == 400
    assert process.poll() is None
    requests_path = Path(str(state["requests_file"]))
    assert not requests_path.exists() or "token=should-not-be-recorded" not in requests_path.read_text()


def test_fixture_fails_closed_for_missing_or_empty_artifact_inputs(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    missing = tmp_path / "missing.nsis.zip"
    signature = tmp_path / "signature.sig"
    signature.write_text("sig\n", encoding="utf-8")
    command = [
        sys.executable,
        str(FIXTURE),
        "--state-file",
        str(state_path),
        "--current-version",
        "0.1.0",
        "--valid-version",
        "0.1.1",
        "--valid-artifact",
        str(missing),
        "--valid-signature",
        str(signature),
        "--invalid-version",
        "0.1.2",
        "--invalid-artifact",
        str(missing),
        "--invalid-signature",
        str(signature),
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "artifact cannot be read" in result.stderr

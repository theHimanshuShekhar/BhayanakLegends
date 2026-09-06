"""Regression tests for smoke request validation, redaction, and cleanup."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_windows_smoke_fixture.py"
PATCHER = REPO_ROOT / "tools" / "patch_updater_endpoint.py"
REDACTOR = REPO_ROOT / "tools" / "redact_diagnostics.py"


def _write_fixture_state(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "valid": {"artifact_route": "/artifacts/valid/valid.nsis.zip"},
                "invalid": {"artifact_route": "/artifacts/invalid/invalid.nsis.zip"},
            }
        ),
        encoding="utf-8",
    )


def _write_requests(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_fixture_checker_requires_both_real_artifact_phases_and_path_only_logs(
    tmp_path: Path,
) -> None:
    requests = tmp_path / "requests.jsonl"
    state = tmp_path / "state.json"
    _write_fixture_state(state)
    _write_requests(
        requests,
        [
            {"method": "GET", "path": "/findings-pack-manifest.json"},
            {"method": "GET", "path": "/findings-pack-manifest.json.sig"},
            {"method": "GET", "path": "/findings-pack.zip"},
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/artifacts/valid/valid.nsis.zip"},
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/artifacts/invalid/invalid.nsis.zip"},
        ],
    )
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(requests), "--state-file", str(state)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "valid and rejected artifacts" in result.stdout


@pytest.mark.parametrize(
    "rows",
    [
        [
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/artifacts/valid/valid.nsis.zip"},
        ],
        [
            {"method": "GET", "path": "/latest.json?secret=token"},
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/artifacts/valid/valid.nsis.zip"},
            {"method": "GET", "path": "/artifacts/invalid/invalid.nsis.zip"},
        ],
        [
            {"method": "GET", "path": "http://example.invalid/latest.json"},
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/artifacts/valid/valid.nsis.zip"},
            {"method": "GET", "path": "/artifacts/invalid/invalid.nsis.zip"},
        ],
        [
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/latest.json"},
            {"method": "GET", "path": "/artifacts/valid/valid.nsis.zip"},
            {"method": "GET", "path": "/artifacts/invalid/invalid.nsis.zip"},
            {"method": "GET", "path": "/findings-pack-manifest.json", "host": "127.0.0.1"},
        ],
    ],
)
def test_fixture_checker_rejects_unsafe_or_incomplete_logs(
    tmp_path: Path, rows: list[dict[str, object]]
) -> None:
    requests = tmp_path / "requests.jsonl"
    state = tmp_path / "state.json"
    _write_fixture_state(state)
    _write_requests(requests, rows)
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(requests), "--state-file", str(state)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_redactor_removes_ephemeral_and_production_credentials(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "redacted"
    source.mkdir()
    (source / "process.log").write_text(
        "TAURI_SIGNING_PRIVATE_KEY=ephemeral-private\n"
        "TAURI_SIGNING_PRIVATE_KEY_PASSWORD='ephemeral-password'\n"
        "production_public_key: production-public\n"
        "token=process-token Bearer bearer-token ghp_github-shaped RGAPI-riot-key\n",
        encoding="utf-8",
    )
    (source / "production-key-backup.txt").write_text(
        "production-key-secret-material", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, str(REDACTOR), str(source), str(destination)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = (destination / "process.log").read_text(encoding="utf-8")
    assert "ephemeral-private" not in output
    assert "ephemeral-password" not in output
    assert "production-public" not in output
    assert "process-token" not in output
    assert "bearer-token" not in output
    assert "ghp_github-shaped" not in output
    assert "RGAPI-riot-key" not in output
    assert (destination / "production-key-backup.txt").read_text(encoding="utf-8") == "[REDACTED KEY MATERIAL]\n"


def _config() -> dict[str, object]:
    return {
        "version": "0.1.0",
        "bundle": {"active": True},
        "plugins": {
            "updater": {
                "endpoints": ["https://release.invalid/latest.json"],
                "pubkey": "production-public-key",
            }
        },
    }


def test_endpoint_patch_updates_pair_and_restore_is_byte_exact(tmp_path: Path) -> None:
    config = tmp_path / "tauri.conf.json"
    backup = tmp_path / "tauri.conf.json.backup"
    public_key = tmp_path / "smoke.pub"
    original = json.dumps(_config(), indent=2) + "\n"
    config.write_text(original, encoding="utf-8")
    public_key.write_text("smoke-public-key\n", encoding="utf-8")

    patched = subprocess.run(
        [
            sys.executable,
            str(PATCHER),
            str(config),
            "--endpoint",
            "http://127.0.0.1:23199/latest.json",
            "--public-key-file",
            str(public_key),
            "--version",
            "0.1.1",
            "--allow-insecure-transport",
            "--backup",
            str(backup),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert patched.returncode == 0, patched.stderr
    document = json.loads(config.read_text(encoding="utf-8"))
    updater = document["plugins"]["updater"]
    assert updater["endpoints"] == ["http://127.0.0.1:23199/latest.json"]
    assert updater["pubkey"] == "smoke-public-key"
    assert updater["dangerousInsecureTransportProtocol"] is True
    assert document["version"] == "0.1.1"

    restored = subprocess.run(
        [sys.executable, str(PATCHER), str(config), "--backup", str(backup), "--restore"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert restored.returncode == 0, restored.stderr
    assert config.read_text(encoding="utf-8") == original
    assert not backup.exists()


def test_endpoint_patch_rejects_non_loopback_and_unapproved_http(tmp_path: Path) -> None:
    config = tmp_path / "tauri.conf.json"
    backup = tmp_path / "backup.json"
    config.write_text(json.dumps(_config()), encoding="utf-8")
    for endpoint, expected in (
        ("http://localhost:23199/latest.json", "literal 127.0.0.1"),
        ("http://127.0.0.1:23199/latest.json?token=secret", "literal 127.0.0.1"),
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(PATCHER),
                str(config),
                "--endpoint",
                endpoint,
                "--backup",
                str(backup),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert expected in result.stderr

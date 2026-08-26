"""Diagnostics-path contract tests: fixture-sequence checker, redaction, and
the endpoint/pubkey/version patcher used to restore production settings on
every exit path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return load_module("check_windows_smoke_fixture", "tools/check_windows_smoke_fixture.py")


@pytest.fixture(scope="module")
def redactor():
    return load_module("redact_diagnostics", "tools/redact_diagnostics.py")


@pytest.fixture(scope="module")
def patcher():
    return load_module("patch_updater_endpoint", "tools/patch_updater_endpoint.py")


# ---------------------------------------------------------------------------
# tools/check_windows_smoke_fixture.py
# ---------------------------------------------------------------------------


def full_valid_rows() -> list[dict[str, str]]:
    return [
        {"method": "GET", "path": "/latest.json"},
        {"method": "GET", "path": "/updater/update.bin"},
        {"method": "GET", "path": "/findings-pack-manifest.json"},
        {"method": "GET", "path": "/findings-pack.zip"},
        {"method": "GET", "path": "/latest.json"},
        {"method": "GET", "path": "/latest.json"},
        {"method": "GET", "path": "/updater/rejected.bin"},
    ]


def test_full_sequence_passes_and_summarizes_counts(checker):
    summary = checker.check_requests(full_valid_rows())
    assert "3 metadata checks" in summary
    assert "1 valid and 1 rejected artifact downloads" in summary


def test_missing_rejected_artifact_fails_because_invalid_phase_unproven(checker):
    rows = [row for row in full_valid_rows() if row["path"] != "/updater/rejected.bin"]
    with pytest.raises(SystemExit, match="rejected-signature artifact download"):
        checker.check_requests(rows)


def test_missing_valid_artifact_fails(checker):
    rows = [row for row in full_valid_rows() if row["path"] != "/updater/update.bin"]
    with pytest.raises(SystemExit, match="valid signed updater artifact"):
        checker.check_requests(rows)


def test_missing_pack_requests_fails(checker):
    rows = [row for row in full_valid_rows() if not row["path"].startswith("/findings-pack")]
    with pytest.raises(SystemExit, match="Findings Pack"):
        checker.check_requests(rows)


def test_non_get_method_fails(checker):
    rows = [*full_valid_rows(), {"method": "POST", "path": "/latest.json"}]
    with pytest.raises(SystemExit, match="unexpected HTTP method"):
        checker.check_requests(rows)


@pytest.mark.parametrize(
    "path",
    [
        "/latest.json?token=leak",
        "/latest.json#frag",
        "/latest.json@evil.example",
    ],
)
def test_query_or_host_bearing_paths_fail(checker, path):
    rows = [*full_valid_rows(), {"method": "GET", "path": path}]
    with pytest.raises(SystemExit, match="query/host data"):
        checker.check_requests(rows)


def test_absolute_url_path_fails_as_not_a_bare_path(checker):
    rows = [*full_valid_rows(), {"method": "GET", "path": "http://evil.example/latest.json"}]
    with pytest.raises(SystemExit, match="not a bare path"):
        checker.check_requests(rows)


def test_unexpected_path_fails(checker):
    rows = [*full_valid_rows(), {"method": "GET", "path": "/etc/passwd"}]
    with pytest.raises(SystemExit, match="unexpected paths"):
        checker.check_requests(rows)


def test_row_with_extra_keys_fails(checker):
    rows = [*full_valid_rows(), {"method": "GET", "path": "/latest.json", "host": "evil.example"}]
    with pytest.raises(SystemExit, match="path-only"):
        checker.check_requests(rows)


def test_main_reads_jsonl_file_and_prints_summary(checker, tmp_path, capsys):
    requests_file = tmp_path / "updater-fixture.requests.jsonl"
    requests_file.write_text("\n".join(json.dumps(row) for row in full_valid_rows()) + "\n", encoding="utf-8")
    sys.argv = ["check_windows_smoke_fixture.py", str(requests_file)]
    checker.main()
    assert "loopback updater proof verified" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# tools/redact_diagnostics.py
# ---------------------------------------------------------------------------


def test_redacts_password_assignment_including_underscore_joined_keys(redactor):
    text = 'TAURI_SIGNING_PRIVATE_KEY_PASSWORD=hunter2-super-secret\nother=fine'
    redacted = redactor.redact(text)
    assert "hunter2-super-secret" not in redacted
    assert "[REDACTED]" in redacted
    assert "other=fine" in redacted


def test_redacts_pem_private_key_block(redactor):
    text = "before\n-----BEGIN PRIVATE KEY-----\nMIIBogIBAAKC...secretmaterial\n-----END PRIVATE KEY-----\nafter"
    redacted = redactor.redact(text)
    assert "secretmaterial" not in redacted
    assert "[REDACTED PRIVATE KEY BLOCK]" in redacted
    assert "before" in redacted and "after" in redacted


def test_redacts_ephemeral_private_key_material(redactor):
    # Real tauri-signer private key files are exactly one line of base64
    # text starting with this fixed "untrusted comment:" prefix.
    text = "before dW50cnVzdGVkIGNvbW1lbnQ6cnNpZ24gZW5jcnlwdGVkIHNlY3JldCBrZXlTRUNSRVRLRVlNQVRFUklBTA== after"
    redacted = redactor.redact(text)
    assert "dW50cnVzdGVkIGNvbW1lbnQ6cnNpZ24gZW5jcnlwdGVkIHNlY3JldCBrZXlTRUNSRVRLRVlNQVRFUklBTA==" not in redacted
    assert "[REDACTED MINISIGN KEY MATERIAL]" in redacted
    assert "before" in redacted and "after" in redacted


def test_redacts_production_pubkey_backup_embedded_in_json(redactor):
    # tauri.conf.json stores pubkey as base64 of the minisign public-key
    # file, so a leaked backup would carry this exact shape inside JSON.
    text = (
        '{"plugins":{"updater":{"pubkey":'
        '"dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDk4N0RCNzkwOUZGRDYyN0EKUldSNll2MmZrTGQ5bUlRNlVWODFrSTl2Mmd1NjZLclhWNFlTNG9aUURDVy9GSFQ3dVhmK3F1SDYK"'
        '}}}'
    )
    redacted = redactor.redact(text)
    assert "RWR6Yv2fkLd9mIQ6UV81kI9v2gu66KrXV4YS4oZQDCW" not in redacted
    assert "[REDACTED MINISIGN KEY MATERIAL]" in redacted
    assert '"pubkey":"[REDACTED MINISIGN KEY MATERIAL]"' in redacted


def test_redacts_riot_api_key(redactor):
    redacted = redactor.redact("key=RGAPI-11111111-2222-3333-4444-555555555555")
    assert "RGAPI-11111111-2222-3333-4444-555555555555" not in redacted
    assert "RGAPI-[REDACTED]" in redacted


def test_redacts_token_bearing_query_string(redactor):
    redacted = redactor.redact("GET /events?token=super-secret-token HTTP/1.1")
    assert "super-secret-token" not in redacted
    assert "?token=[REDACTED]" in redacted


def test_leaves_ordinary_diagnostic_text_unchanged(redactor):
    text = '{"phase": "updated", "result": "passed", "sidecar_port": 51234}'
    assert redactor.redact(text) == text


def test_main_redacts_tree_and_honors_extra_secrets_env(redactor, tmp_path, monkeypatch):
    source = tmp_path / "src"
    destination = tmp_path / "dst"
    source.mkdir()
    (source / "state.json").write_text('{"note": "the-random-password-abc123 leaked here"}', encoding="utf-8")
    binary = source / "blob.bin"
    binary.write_bytes(bytes(range(256)))

    monkeypatch.setenv("REDACT_EXTRA_SECRETS", "the-random-password-abc123")
    sys.argv = ["redact_diagnostics.py", str(source), str(destination)]
    redactor.main()

    redacted_text = (destination / "state.json").read_text(encoding="utf-8")
    assert "the-random-password-abc123" not in redacted_text
    assert (destination / "blob.bin").exists()


def test_main_is_a_no_op_when_source_is_absent(redactor, tmp_path):
    destination = tmp_path / "dst"
    sys.argv = ["redact_diagnostics.py", str(tmp_path / "does-not-exist"), str(destination)]
    redactor.main()
    assert destination.is_dir()
    assert list(destination.iterdir()) == []


# ---------------------------------------------------------------------------
# tools/patch_updater_endpoint.py
# ---------------------------------------------------------------------------


def make_production_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "plugins": {
                    "updater": {
                        "endpoints": ["https://github.example/releases/latest/download/latest.json"],
                        "pubkey": "production-public-key-base64",
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_apply_patch_replaces_endpoint_pubkey_and_enables_insecure_transport(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    backup = tmp_path / "tauri.conf.json.smoke-backup"
    make_production_config(config)
    original_bytes = config.read_bytes()

    patcher.apply_patch(
        config,
        backup=backup,
        endpoint="http://127.0.0.1:24987/latest.json",
        pubkey="ephemeral-job-local-pubkey",
    )

    patched = json.loads(config.read_text(encoding="utf-8"))
    updater = patched["plugins"]["updater"]
    assert updater["endpoints"] == ["http://127.0.0.1:24987/latest.json"]
    assert updater["pubkey"] == "ephemeral-job-local-pubkey"
    assert updater["dangerousInsecureTransportProtocol"] is True
    assert backup.read_bytes() == original_bytes


def test_restore_reverts_to_byte_identical_production_config(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    backup = tmp_path / "tauri.conf.json.smoke-backup"
    make_production_config(config)
    original_bytes = config.read_bytes()

    patcher.apply_patch(
        config, backup=backup, endpoint="http://127.0.0.1:1/latest.json", pubkey="ephemeral"
    )
    assert config.read_bytes() != original_bytes

    patcher.restore(backup, config)
    assert config.read_bytes() == original_bytes


def test_restore_without_backup_is_a_safe_no_op(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    make_production_config(config)
    original_bytes = config.read_bytes()
    patcher.restore(tmp_path / "missing-backup", config)
    assert config.read_bytes() == original_bytes


def test_apply_patch_refuses_non_loopback_endpoint(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    make_production_config(config)
    with pytest.raises(SystemExit, match="loopback-only"):
        patcher.apply_patch(
            config,
            backup=tmp_path / "backup",
            endpoint="http://evil.example/latest.json",
            pubkey="ephemeral",
        )


def test_apply_patch_refuses_empty_pubkey(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    make_production_config(config)
    with pytest.raises(SystemExit, match="public key"):
        patcher.apply_patch(
            config, backup=tmp_path / "backup", endpoint="http://127.0.0.1:1/latest.json", pubkey="   "
        )


def test_apply_patch_refuses_to_overwrite_existing_backup(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    backup = tmp_path / "backup"
    make_production_config(config)
    backup.write_text("pre-existing", encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to overwrite existing backup"):
        patcher.apply_patch(
            config, backup=backup, endpoint="http://127.0.0.1:1/latest.json", pubkey="ephemeral"
        )
    assert backup.read_text(encoding="utf-8") == "pre-existing"


def test_apply_patch_refuses_config_with_no_production_pubkey_to_protect(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    config.write_text(
        json.dumps({"plugins": {"updater": {"endpoints": ["https://example/latest.json"], "pubkey": ""}}}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="production pubkey"):
        patcher.apply_patch(
            config, backup=tmp_path / "backup", endpoint="http://127.0.0.1:1/latest.json", pubkey="ephemeral"
        )


def test_set_version_mutates_only_the_version_field(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    make_production_config(config)
    before = json.loads(config.read_text(encoding="utf-8"))

    sys.argv = ["patch_updater_endpoint.py", str(config), "--set-version", "0.2.0"]
    patcher.main()

    after = json.loads(config.read_text(encoding="utf-8"))
    assert after["version"] == "0.2.0"
    after["version"] = before["version"]
    assert after == before


def test_main_patch_then_restore_round_trips_via_cli(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    backup = tmp_path / "tauri.conf.json.smoke-backup"
    make_production_config(config)
    original_bytes = config.read_bytes()

    sys.argv = [
        "patch_updater_endpoint.py",
        str(config),
        "--endpoint",
        "http://127.0.0.1:24987/latest.json",
        "--pubkey",
        "ephemeral-pubkey",
        "--backup",
        str(backup),
    ]
    patcher.main()
    assert config.read_bytes() != original_bytes

    sys.argv = ["patch_updater_endpoint.py", str(config), "--backup", str(backup), "--restore"]
    patcher.main()
    assert config.read_bytes() == original_bytes


def test_main_rejects_set_version_combined_with_restore(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    make_production_config(config)
    sys.argv = [
        "patch_updater_endpoint.py",
        str(config),
        "--backup",
        str(tmp_path / "backup"),
        "--restore",
        "--set-version",
        "0.2.0",
    ]
    with pytest.raises(SystemExit, match="--set-version"):
        patcher.main()


def test_main_rejects_endpoint_without_pubkey(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    make_production_config(config)
    sys.argv = [
        "patch_updater_endpoint.py",
        str(config),
        "--endpoint",
        "http://127.0.0.1:1/latest.json",
        "--backup",
        str(tmp_path / "backup"),
    ]
    with pytest.raises(SystemExit, match="together"):
        patcher.main()


def test_main_rejects_set_version_combined_with_endpoint(patcher, tmp_path):
    config = tmp_path / "tauri.conf.json"
    make_production_config(config)
    sys.argv = [
        "patch_updater_endpoint.py",
        str(config),
        "--endpoint",
        "http://127.0.0.1:1/latest.json",
        "--pubkey",
        "ephemeral",
        "--backup",
        str(tmp_path / "backup"),
        "--set-version",
        "0.2.0",
    ]
    with pytest.raises(SystemExit, match="--set-version"):
        patcher.main()

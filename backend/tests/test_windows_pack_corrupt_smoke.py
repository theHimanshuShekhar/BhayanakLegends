"""Focused contracts for the packaged Windows Findings Pack rollback proof."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "windows-smoke.yml"
HELPER = REPO_ROOT / "tools" / "windows_pack_corrupt_smoke.py"
FIXTURE = REPO_ROOT / "tools" / "windows_updater_fixture.py"
POWERSHELL = REPO_ROOT / "tools" / "windows_packaged_smoke.ps1"
NODE = REPO_ROOT / "tools" / "windows_packaged_smoke.mjs"


def test_workflow_runs_distinct_bounded_pack_rollback_and_updater_proofs() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    pack_proof = workflow.index("tools/windows_pack_corrupt_smoke.py run")
    packaged_app = workflow.index("pwsh -File tools/windows_packaged_smoke.ps1")
    updater_flip = workflow.index("-FlipFile \"$env:SMOKE_FLIP_FILE\"")
    assert pack_proof < packaged_app <= updater_flip
    assert "--valid-manifest-url $manifestUrl" in workflow
    assert "--corrupt-manifest-url $corruptManifestUrl" in workflow
    assert "--manifest-public-key $manifestPublicKey" in workflow
    assert "restart_retained_generation" in workflow
    assert "restart_retained_version" in workflow
    assert "restart_retained_hash" in workflow
    assert 'Join-Path $env:RUNNER_TEMP "bl-pack-store-smoke"' in workflow
    assert 'Remove-Item $env:SMOKE_ARTIFACTS -Recurse -Force' in workflow
    assert 'Remove-Item Env:BHAYANAK_PACK_RELEASE_MANIFEST_URL' in workflow
    assert 'Remove-Item Env:BHAYANAK_PACK_RELEASE_MANIFEST_PUBLIC_KEY' in workflow
    assert "SMOKE_PACK_VERSION=$packVersion" in workflow
    assert '-ExpectedPackVersion "$env:SMOKE_PACK_VERSION"' in workflow
    assert "windows_packaged_smoke.mjs" in POWERSHELL.read_text(encoding="utf-8")
    assert "assertPackContract" in NODE.read_text(encoding="utf-8")
    assert 'Remove-Item (Join-Path $env:RUNNER_TEMP "bl-pack-store-smoke")' in workflow
    assert "invalid_retention" in POWERSHELL.read_text(encoding="utf-8")
    assert "version_unchanged" in POWERSHELL.read_text(encoding="utf-8")
    assert "hash_unchanged" in POWERSHELL.read_text(encoding="utf-8")
    assert "sidecar_healthy" in POWERSHELL.read_text(encoding="utf-8")
    assert '--smoke-state "$env:SMOKE_DIAGNOSTICS\\smoke-state.json"' in workflow
def test_packaged_smoke_security_matrix_is_wired_without_raw_token_output() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    powershell = POWERSHELL.read_text(encoding="utf-8")
    node = NODE.read_text(encoding="utf-8")
    checker = (REPO_ROOT / "tools" / "check_windows_smoke_fixture.py").read_text(encoding="utf-8")
    assert "-DiagnosticsDir \"$env:SMOKE_DIAGNOSTICS\"" in workflow
    assert "-ImportRoot \"$env:SMOKE_IMPORT_ROOT\"" in workflow
    assert 'BHAYANAK_ALLOW_IMPORT = "true"' in powershell
    assert "BHAYANAK_IMPORT_ROOTS" in powershell
    assert "invalid-token-valid-host" in node
    assert "valid-token-invalid-host" in node
    assert "dev import disabled" in node
    assert "/events?token=" in node
    assert "assertDiagnosticsSafe" in node
    assert "sidecar-security-" in checker
    assert 'token="' in checker
    assert "token: { length" in node
    assert "console.log(JSON.stringify({ phase, ...result }))" in node
    assert "--require-security" in checker


def test_pack_rollback_helper_uses_real_release_channel_store_and_subprocess_restart() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "ReleaseChannel(" in source
    assert "PackStore(" in source
    assert "result = await channel.check_and_activate(current_version)" in source
    assert "_run_candidate(restarted, corrupt_manifest_url, public_key, version)" in source
    assert "subprocess.run(command" in source
    assert '"verify"' in source
    assert "InferenceRuntime(store)" in source
    assert "runtime.predict(model_key, baseline" in source
    assert "runtime.what_if({}, baseline" in source
    assert "available_model_keys" in source
    assert "corrupt Findings Pack candidate unexpectedly activated" in source
    assert "expected_generation" in source
    assert "expected_hash" in source


def test_pack_corrupt_manifest_is_manifest_only_newer_and_sidecar_executes_all_models() -> None:
    fixture = FIXTURE.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    node = NODE.read_text(encoding="utf-8")
    assert 'corrupt_manifest_payload["pack_version"] = "v5-smoke-invalid-129"' in fixture
    assert '"smoke_only_invalid_candidate"' in fixture
    assert "artifact_bytes_differ" in fixture
    assert "signature_reused" in fixture
    assert "_run_candidate(restarted, corrupt_manifest_url, public_key, version)" in helper
    assert "for model_key, declaration in available.items()" in helper
    assert 'results.get("personal_what_if")' in helper
    assert 'model.key === "personal_what_if" ? "/history/what-if" : "/live/ingame"' in node
    assert 'waitUpdaterFailure(page, "signature"' in node
    assert 'data-updater-error-kind' in node


def test_pack_corruption_is_not_conflated_with_updater_signature_rejection() -> None:
    fixture = FIXTURE.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    powershell = POWERSHELL.read_text(encoding="utf-8")
    node = NODE.read_text(encoding="utf-8")
    assert "findings-pack-corrupt" in fixture
    assert "corrupt_manifest_url" in helper
    assert "signature does not match its bytes" in powershell
    assert 'waitUpdaterFailure(page, "signature"' in node
    assert "findings-pack-corrupt" not in powershell
    assert "findings-pack-corrupt" not in node
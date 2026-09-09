"""Contract tests for the signed updater release workflow."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import tomllib
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "src-tauri" / "tauri.conf.json"
RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _workflow_blocks() -> list[str]:
    lines = RELEASE.read_text(encoding="utf-8").splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^      - (?:name|run|uses):", line)
    ]
    blocks: list[str] = []
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[start:end]))
    return blocks


def _workflow_steps() -> dict[str, str]:
    steps: dict[str, str] = {}
    for block in _workflow_blocks():
        first_line = block.splitlines()[0]
        match = re.match(r"^      - name: (.+)$", first_line)
        if match:
            steps[match.group(1)] = block
    return steps


def _workflow_step(name: str) -> str:
    try:
        return _workflow_steps()[name]
    except KeyError as exc:
        raise AssertionError(f"workflow step is missing: {name}") from exc


def _step_order() -> list[str]:
    names: list[str] = []
    for block in _workflow_blocks():
        match = re.match(r"^      - name: (.+)$", block.splitlines()[0])
        if match:
            names.append(match.group(1))
    return names


def _decode_tauri_signature_wrapper(wrapper: bytes) -> tuple[bytes, bytes, bytes]:
    minisign_text = base64.b64decode(wrapper.strip(), validate=True).decode("ascii")
    lines = minisign_text.splitlines()
    if (
        len(lines) != 4
        or not lines[0].startswith("untrusted comment: ")
        or not lines[2].startswith("trusted comment: ")
    ):
        raise AssertionError("unexpected Minisign wrapper shape")
    primary = base64.b64decode(lines[1].strip(), validate=True)
    trusted_comment = lines[2][len("trusted comment: ") :].strip().encode("ascii")
    global_signature = base64.b64decode(lines[3].strip(), validate=True)
    return primary, global_signature, trusted_comment


def test_tauri_signature_wrapper_verifies_prehashed_primary_and_global_signatures():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    message = b"Bhayanak Legends updater signing probe\n"
    key_id = b"keyid001"
    digest = hashlib.blake2b(message, digest_size=64).digest()
    public_blob = b"Ed" + key_id + public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    primary = b"ED" + key_id + private_key.sign(digest)
    trusted_comment = "trusted comment: timestamp: 1"
    trusted_bytes = trusted_comment[len("trusted comment: ") :].encode("ascii")
    global_signature = private_key.sign(primary[10:] + trusted_bytes)
    signature_file = "\n".join(
        (
            "untrusted comment: signature from minisign secret key",
            base64.b64encode(primary).decode("ascii"),
            trusted_comment,
            base64.b64encode(global_signature).decode("ascii"),
        )
    ).encode("ascii")

    payload, global_blob, parsed_trusted = _decode_tauri_signature_wrapper(
        base64.b64encode(signature_file) + b"\n"
    )
    assert len(payload) == 74
    assert payload[:2] == b"ED"
    assert public_blob[:2] == b"Ed"
    assert public_blob[:10] != payload[:10]
    assert public_blob[2:10] == payload[2:10]
    verifier = Ed25519PublicKey.from_public_bytes(public_blob[10:])
    try:
        verifier.verify(payload[10:], message)
    except InvalidSignature:
        pass
    else:
        raise AssertionError("raw-message verification unexpectedly accepted a prehashed signature")
    verifier.verify(payload[10:], digest)
    verifier.verify(global_blob, payload[10:] + parsed_trusted)
    corrupted_global = bytearray(global_blob)
    corrupted_global[-1] ^= 0x01
    try:
        verifier.verify(bytes(corrupted_global), payload[10:] + parsed_trusted)
    except InvalidSignature:
        pass
    else:
        raise AssertionError("corrupted Minisign global signature unexpectedly verified")

    for name in (
        "Verify updater signing prerequisites",
        "Verify draft release contents before promotion",
        "Verify anonymous latest release endpoints",
    ):
        step = _workflow_step(name)
        assert "len(lines) != 4" in step
        assert "public_blob[:2] != b\"Ed\"" in step
        assert "signature_blob[:2] != b\"ED\"" in step
        assert "public_blob[2:10] != signature_blob[2:10]" in step
        assert ".encode(\"ascii\")" in step
        assert "blake2b" in step
        assert "global_signature" in step


def test_updater_artifacts_enabled_in_tauri_config():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    bundle = config["bundle"]
    assert bundle.get("createUpdaterArtifacts") is True
    pubkey = config["plugins"]["updater"]["pubkey"]
    assert isinstance(pubkey, str) and len(pubkey) > 100


def test_all_release_version_sources_are_aligned():
    expected = "0.1.9"
    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads(CONFIG.read_text(encoding="utf-8"))
    backend = tomllib.loads(
        (REPO_ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    )
    cargo = tomllib.loads(
        (REPO_ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
    )
    backend_lock = tomllib.loads(
        (REPO_ROOT / "backend/uv.lock").read_text(encoding="utf-8")
    )
    cargo_lock = tomllib.loads(
        (REPO_ROOT / "src-tauri/Cargo.lock").read_text(encoding="utf-8")
    )
    backend_lock_version = next(
        entry["version"]
        for entry in backend_lock["package"]
        if entry.get("name") == "bhayanak-legends"
    )
    cargo_lock_version = next(
        entry["version"]
        for entry in cargo_lock["package"]
        if entry.get("name") == "bhayanak-legends"
    )
    from bhayanak_legends.version import APP_VERSION

    versions = {
        "package.json": package["version"],
        "src-tauri/tauri.conf.json": tauri["version"],
        "backend/pyproject.toml": backend["project"]["version"],
        "backend/uv.lock": backend_lock_version,
        "src-tauri/Cargo.toml": cargo["package"]["version"],
        "src-tauri/Cargo.lock": cargo_lock_version,
        "backend runtime": APP_VERSION,
    }
    assert versions == {source: expected for source in versions}


def test_windows_run_steps_declare_explicit_shells():
    blocks = _workflow_blocks()
    run_steps = [block for block in blocks if re.search(r"^        run:", block, re.MULTILINE)]
    assert run_steps
    assert all(
        re.search(r"^        shell: (?:bash|pwsh)$", block, re.MULTILINE)
        for block in run_steps
    )

    checker = _workflow_step("Check Windows updater artifacts")
    assert "LATEST_JSON_PATH: ${{ runner.temp }}/latest.json" in checker
    assert 'RUNNER_TEMP_MSYS="$(cygpath -u "$RUNNER_TEMP")"' in checker
    assert 'STAGED_BUNDLE_DIR_NATIVE="$(cygpath -m "$STAGED_BUNDLE_DIR_MSYS")"' in checker
    assert 'VERSION="${GITHUB_REF_NAME#v}"' in checker
    assert '--latest-json "$LATEST_JSON_PATH_NATIVE"' in checker
    assert '--version "$VERSION"' in checker

    signing = _workflow_step("Verify updater signing prerequisites")
    assert re.search(r"^        shell: bash$", signing, re.MULTILINE)
    assert "trap 'rm -f" in signing


def test_release_job_requires_signing_secret_and_cryptographic_prerequisites():
    text = RELEASE.read_text(encoding="utf-8")
    prerequisites = _workflow_step("Verify updater signing prerequisites")
    assert "TAURI_SIGNING_PRIVATE_KEY:" in prerequisites
    assert "TAURI_SIGNING_PRIVATE_KEY_PASSWORD:" in prerequisites
    assert "createUpdaterArtifacts" in prerequisites
    assert 'pnpm tauri signer sign "$PROBE_FILE_NATIVE"' in prerequisites
    assert "--private-key" not in prerequisites
    assert "--password" not in prerequisites
    assert "Ed25519PublicKey" in prerequisites
    assert "len(primary) != 74" in prerequisites
    assert "len(global_signature) != 64" in prerequisites
    assert "public_blob[:2] != b\"Ed\"" in prerequisites
    assert "signature_blob[:2] != b\"ED\"" in prerequisites
    assert "public_blob[2:10] != signature_blob[2:10]" in prerequisites
    assert "signature_blob[10:]" in prerequisites
    assert "blake2b" in prerequisites
    assert "global_signature" in prerequisites
    assert "verify(" in prerequisites
    assert "python3 -" not in prerequisites
    assert not re.search(r"^\s*(?:echo|printf).*\$TAURI_SIGNING_", prerequisites, re.MULTILINE)
    assert "--clobber" not in text


def test_release_tag_gate_and_immutable_slot_precede_build():
    gate = _workflow_step("Verify release tag version")
    assert 'TAG="$GITHUB_REF_NAME"' in gate
    assert 'VERSION="${TAG#v}"' in gate
    assert 'Path("package.json")' in gate
    assert 'Path("src-tauri/tauri.conf.json")' in gate
    assert 'Path("src-tauri/Cargo.toml")' in gate
    assert 'Path("src-tauri/Cargo.lock")' in gate
    assert 'Path("backend/pyproject.toml")' in gate
    assert 'Path("backend/uv.lock")' in gate
    assert "from bhayanak_legends.version import APP_VERSION" in gate
    assert "versions = {" in gate
    assert "mismatches = {" in gate
    assert "version != expected" in gate

    immutable = _workflow_step("Verify immutable release tag and empty release slot")
    assert "gh api" in immutable
    assert "GITHUB_SHA" in immutable
    # The pre-creation slot check is the only tag-addressed release query.
    assert 'gh release view "$TAG"' in immutable
    assert "gh release edit" not in immutable

    order = _step_order()
    assert order.index("Verify release tag version") < order.index("Build Python sidecar binary")
    assert order.index("Verify immutable release tag and empty release slot") < order.index(
        "Build Python sidecar binary"
    )


def test_release_draft_is_verified_before_promotion():
    order = _step_order()
    inventory = order.index("Inventory exact updater assets before draft creation")
    create = order.index("Create signed release draft")
    upload = order.index("Upload exact updater and Findings Pack assets to draft")
    verify = order.index("Verify draft release contents before promotion")
    promote = order.index("Promote verified release draft")
    anonymous = order.index("Verify anonymous latest release endpoints")
    rollback = order.index("Re-draft release after a failed publication check")
    assert inventory < create < upload < verify < promote < anonymous < rollback

    inventory_step = _workflow_step("Inventory exact updater assets before draft creation")
    assert "exactly one file" in inventory_step
    assert "exactly one signed updater candidate" in inventory_step
    assert "release-inventory.json" in inventory_step
    assert "dict.fromkeys" in inventory_step
    assert '"assets": asset_names' in inventory_step
    assert "latest.json does not reference the unique updater archive" in inventory_step

    create_step = _workflow_step("Create signed release draft")
    assert "id: create" in create_step
    assert "gh api" in create_step
    assert "--method POST" in create_step
    assert 'releases" > "$CREATE_RESPONSE_MSYS"' in create_step
    assert '--field "draft=true"' in create_step
    assert "target_commitish" in create_step
    assert "upload_url" in create_step
    assert "uploads.github.com" in create_step
    assert "{?name,label}" in create_step
    assert "urlsplit" in create_step
    assert "--verify-tag" not in create_step
    assert "gh release create" not in create_step
    assert "release-identity" in create_step

    upload_step = _workflow_step("Upload exact updater and Findings Pack assets to draft")
    assert "gh api" in upload_step
    assert "findings-pack.v2.zip" in upload_step
    assert "findings-pack-manifest.json" in upload_step
    assert "findings-pack-manifest.json.sig" in upload_step
    assert 'EXPECTED_UPLOAD_URL="https://uploads.github.com/repos/${GITHUB_REPOSITORY}/releases/${RELEASE_ID}/assets"' in upload_step
    assert "UPLOAD_URL" in upload_step
    assert 'ASSET_PATH_CURL="$(cygpath -m "$asset_path")"' in upload_step
    assert 'RUNNER_TEMP_MSYS="$(cygpath -u "$RUNNER_TEMP")"' in upload_step
    assert 'STAGED_BUNDLE_DIR_MSYS="$RUNNER_TEMP_MSYS/updater-bundle"' in upload_step
    assert 'INVENTORY_PATH_MSYS="$RUNNER_TEMP_MSYS/release-inventory.json"' in upload_step
    assert 'INVENTORY_PATH_NATIVE="$(cygpath -m "$INVENTORY_PATH_MSYS")"' in upload_step
    for name in (
        "Build canonical Findings Pack release payload",
        "Sign Findings Pack manifest",
        "Verify generated Findings Pack payload",
        "Verify updater signing prerequisites",
        "Stage canonical Windows updater assets",
        "Check Windows updater artifacts",
        "Inventory exact updater assets before draft creation",
        "Create signed release draft",
        "Verify draft release contents before promotion",
        "Promote verified release draft",
        "Verify anonymous latest release endpoints",
        "Re-draft release after a failed publication check",
    ):
        assert 'RUNNER_TEMP_MSYS="$(cygpath -u "$RUNNER_TEMP")"' in _workflow_step(name)
    assert "ASSET_PATH_CURL" in upload_step
    assert "--config -" in upload_step
    assert 'Authorization: Bearer ${GH_TOKEN}' in upload_step
    assert 'data-binary = "@${ASSET_PATH_CURL}"' in upload_step
    assert 'data-binary = "@${asset_path}"' not in upload_step
    assert 'url = "${UPLOAD_URL}?name=${asset_name}"' in upload_step
    assert "inventory.get(\"assets\")" in upload_step
    assert "len(set(assets)) != len(assets)" in upload_step
    assert "--method POST" not in upload_step
    assert 'releases/${RELEASE_ID}/assets?name=${asset_name}' not in upload_step
    assert "release identity or draft state changed before asset upload" in upload_step
    assert "--clobber" not in upload_step
    assert "gh release upload" not in upload_step
    verify_step = _workflow_step("Verify draft release contents before promotion")
    assert "gh api" in verify_step
    assert "releases/${RELEASE_ID}/assets?per_page=100" in verify_step
    assert "releases/assets/${asset_id}" in verify_step
    assert "--pattern" not in verify_step
    assert "gh release download" not in verify_step
    assert "check_windows_updater_artifacts.py" in verify_step
    assert "cmp -s" in verify_step
    assert "Ed25519PublicKey" in verify_step
    assert "verify_manifest_signature" in verify_step
    assert "sha256" in verify_step
    assert "blake2b" in verify_step
    assert "global_signature" in verify_step
    assert "expected_version" in verify_step
    assert "findings-pack-manifest.json.sig" in verify_step
    promote_step = _workflow_step("Promote verified release draft")
    assert "id: promote" in promote_step
    assert "gh api" in promote_step
    assert "--method PATCH" in promote_step
    assert "releases/${EXPECTED_RELEASE_ID}" in promote_step
    assert "release-identity" in promote_step
    assert "release-promotion-attempt" in promote_step
    assert "release-promotion-marker" in promote_step
    assert '--field "draft=false"' in promote_step
    assert ".draft" in promote_step
    assert "gh release edit" not in promote_step


def test_anonymous_latest_endpoints_are_checked_after_promotion():
    anonymous = _workflow_step("Verify anonymous latest release endpoints")
    assert re.search(r"^        shell: bash$", anonymous, re.MULTILINE)
    assert "GH_TOKEN" not in anonymous
    assert "GITHUB_TOKEN" not in anonymous
    assert "releases/latest/download" in anonymous
    assert "curl" in anonymous
    assert "--location" in anonymous
    assert "--proto '=https'" in anonymous
    assert "check_windows_updater_artifacts.py" in anonymous
    assert "verify_manifest_signature" in anonymous
    assert "Ed25519PublicKey" in anonymous
    assert "signature_blob[10:]" in anonymous
    assert "blake2b" in anonymous
    assert "global_signature" in anonymous
    assert "trap 'rm -rf \"$PUBLIC_DIR\"' EXIT" in anonymous


def test_failed_publication_check_returns_release_to_draft_only_for_owned_release():
    recovery = _workflow_step("Re-draft release after a failed publication check")
    assert "if: ${{ failure() && steps.create.outcome == 'success' }}" in recovery
    assert "release-promotion-attempt" in recovery
    assert "release-identity" in recovery
    assert "promotion attempt is not owned by this run" in recovery
    assert "current release identity differs" in recovery
    assert "GH_TOKEN:" in recovery
    assert "gh api" in recovery
    assert "--method PATCH" in recovery
    assert "releases/${EXPECTED_RELEASE_ID}" in recovery
    assert "gh release view" not in recovery
    assert "gh release edit" not in recovery
    assert "this run did not attempt promotion; nothing to roll back" in recovery
    assert '[[ "$CURRENT_IS_DRAFT" == "true" ]]' in recovery
    # A gate/build/upload/validation failure cannot mutate a pre-existing release.
    assert "steps.promote.outcome == 'success'" not in recovery

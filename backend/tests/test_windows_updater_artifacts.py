"""Contract tests for signed Windows updater artifact publication."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import threading
import sys
import textwrap
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    archive = bundle / "Bhayanak Legends_0.1.13_x64-setup.exe"
    archive.write_bytes(b"signed installer bytes")
    signature = archive.with_name(archive.name + ".sig")
    signature_text = "detached-signature-content"
    signature.write_text(signature_text, encoding="utf-8")
    metadata = tmp_path / "latest.json"
    metadata.write_text(
        json.dumps(
            {
                "version": "0.1.13",
                "platforms": {
                    "windows-x86_64": {
                        "signature": signature_text,
                        "url": "https://github.example/releases/download/v0.1.13/"
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





def test_upload_transaction_validates_paths_identity_and_api(tmp_path: Path, capsys):
    source = _workflow_python(
        "Upload exact updater and Findings Pack assets to draft",
        marker="          import json",
    )
    module_path = tmp_path / "upload_transaction.py"
    module_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("upload_transaction", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    version = "0.1.13"
    tag = f"v{version}"
    repository = "theHimanshuShekhar/BhayanakLegends"
    token = "test-token-123456789012345678901234"
    runner_temp = tmp_path / "native-temp"
    staged_dir = runner_temp / "updater-bundle"
    staged_dir.mkdir(parents=True)
    updater_names = [
        f"bhayanak-legends-{version}-windows-x86_64-setup.exe",
        f"bhayanak-legends-{version}-windows-x86_64-setup.exe.sig",
    ]
    fixed_assets = {
        "latest.json": b'{"version":"0.1.13"}',
        "findings-pack.v2.zip": b"findings-pack-bytes",
        "findings-pack-manifest.json": b'{"size":19}',
        "findings-pack-manifest.json.sig": b"manifest-signature",
    }
    asset_bytes = {
        **{name: f"bytes-{name}".encode() for name in updater_names},
        **fixed_assets,
    }
    for name in updater_names:
        (staged_dir / name).write_bytes(asset_bytes[name])
    for name, content in fixed_assets.items():
        (runner_temp / name).write_bytes(content)
    inventory_path = runner_temp / "release-inventory.json"
    inventory_path.write_text(json.dumps({"assets": updater_names}) + "\n", encoding="utf-8")
    identity_path = runner_temp / "release-identity"
    identity_path.write_text(
        f"{tag}\n123\nhttps://uploads.github.com/repos/{repository}/releases/123/assets\n",
        encoding="utf-8",
    )

    class Response:
        def __init__(self, status: int, payload: dict[str, object]):
            self.status = status
            self.body = json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.body

    class Opener:
        def __init__(self, release: dict[str, object], uploads: list[dict[str, object]]):
            self.release = release
            self.uploads = uploads
            self.requests: list[object] = []

        def __call__(self, request):
            self.requests.append(request)
            if request.get_method() == "GET":
                return Response(200, self.release)
            upload_index = sum(
                1 for previous in self.requests[:-1] if previous.get_method() == "POST"
            )
            return Response(201, self.uploads[upload_index])

    release = {"id": 123, "tag_name": tag, "draft": True, "assets": []}
    responses = [
        {"id": 100 + index, "name": name}
        for index, name in enumerate([*updater_names, *fixed_assets])
    ]
    opener = Opener(release, responses)
    module.upload_release(
        runner_temp,
        inventory_path,
        identity_path,
        tag,
        repository,
        token,
        opener=opener,
    )
    output = capsys.readouterr()
    assert token not in output.out + output.err
    assert len(opener.requests) == 1 + len(responses)
    get_request = opener.requests[0]
    assert get_request.get_method() == "GET"
    assert get_request.full_url == f"https://api.github.com/repos/{repository}/releases/123"
    get_headers = {key.lower(): value for key, value in get_request.header_items()}
    assert get_headers["accept"] == "application/vnd.github+json"
    assert get_headers["authorization"] == f"Bearer {token}"
    for request, (name, content) in zip(opener.requests[1:], asset_bytes.items()):
        assert request.get_method() == "POST"
        assert request.full_url == (
            f"https://uploads.github.com/repos/{repository}/releases/123/assets"
            f"?name={quote(name, safe='')}"
        )
        assert request.data == content
        headers = {key.lower(): value for key, value in request.header_items()}
        assert headers["accept"] == "application/vnd.github+json"
        assert headers["authorization"] == f"Bearer {token}"
        assert headers["content-type"] == "application/octet-stream"

    existing = Opener(
        {**release, "assets": [{"id": 999, "name": "already-there.exe"}]},
        responses,
    )
    with pytest.raises(SystemExit, match="already has assets"):
        module.upload_release(
            runner_temp,
            inventory_path,
            identity_path,
            tag,
            repository,
            token,
            opener=existing,
        )
    assert len(existing.requests) == 1

    missing_name = "findings-pack.v2.zip"
    (runner_temp / missing_name).unlink()
    missing = Opener(release, responses)
    with pytest.raises(SystemExit, match="required local release asset is missing"):
        module.upload_release(
            runner_temp,
            inventory_path,
            identity_path,
            tag,
            repository,
            token,
            opener=missing,
        )
    assert all(request.get_method() == "GET" for request in missing.requests)
    (runner_temp / missing_name).write_bytes(fixed_assets[missing_name])

    wrong_name = Opener(release, [{**responses[0], "name": "wrong-name.exe"}, *responses[1:]])
    with pytest.raises(SystemExit, match="wrong asset"):
        module.upload_release(
            runner_temp,
            inventory_path,
            identity_path,
            tag,
            repository,
            token,
            opener=wrong_name,
        )
    assert len(wrong_name.requests) == 2

    duplicate_id = Opener(
        release,
        [{**response, "id": 100} for response in responses],
    )
    with pytest.raises(SystemExit, match="duplicate asset ID"):
        module.upload_release(
            runner_temp,
            inventory_path,
            identity_path,
            tag,
            repository,
            token,
            opener=duplicate_id,
        )
    assert len(duplicate_id.requests) == 3
    redirect_requests: list[tuple[str, str | None]] = []

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            redirect_requests.append((self.path, self.headers.get("Authorization")))
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{self.server.server_port}/location",
            )
            self.end_headers()

        def log_message(self, *_args) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        redirect_request = module.Request(
            f"http://127.0.0.1:{server.server_port}/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        with pytest.raises(SystemExit, match="HTTP 302"):
            module.request_json(
                module.NO_REDIRECT_OPENER.open,
                redirect_request,
                "redirect probe",
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert redirect_requests == [("/start", f"Bearer {token}")]
    output = capsys.readouterr()
    assert token not in output.out + output.err


def test_draft_asset_listing_retries_subset_but_rejects_extra(tmp_path: Path):
    source = _workflow_python(
        "Verify draft release contents before promotion",
        marker="          # DRAFT_ASSET_VERIFICATION_TRANSACTION",
    )
    module_path = tmp_path / "draft_asset_verification.py"
    module_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("draft_asset_verification", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    expected_names = ["latest.json", "updater.exe", "updater.exe.sig"]

    def asset(asset_id: int, name: str) -> dict[str, object]:
        return {"id": asset_id, "name": name, "release": {"id": 123}}

    complete_assets = [
        asset(10, expected_names[0]),
        asset(11, expected_names[1]),
        asset(12, expected_names[2]),
    ]
    responses = iter([[complete_assets[:2]], [complete_assets]])
    fetch_calls = 0
    current_time = 0.0
    request_timeouts: list[float] = []
    sleeps: list[float] = []

    def fetch_subset_then_complete(timeout: float) -> list[object]:
        nonlocal fetch_calls
        request_timeouts.append(timeout)
        fetch_calls += 1
        return next(responses)

    def clock() -> float:
        return current_time

    def sleep(delay: float) -> None:
        nonlocal current_time
        sleeps.append(delay)
        current_time += delay

    asset_map_path = tmp_path / "asset-map.json"
    module.verify_asset_listing_until_complete(
        fetch_subset_then_complete,
        asset_map_path,
        123,
        expected_names,
        clock=clock,
        sleep=sleep,
        deadline_seconds=5,
        backoff_seconds=2,
    )
    assert fetch_calls == 2
    assert request_timeouts == [5, 3]
    assert sleeps == [2]
    assert json.loads(asset_map_path.read_text(encoding="utf-8")) == {
        name: asset_id for asset_id, name in zip((10, 11, 12), expected_names)
    }

    extra_calls = 0
    extra_map_path = tmp_path / "extra-asset-map.json"

    def fetch_extra(timeout: float) -> list[object]:
        nonlocal extra_calls
        extra_calls += 1
        return [[*complete_assets, asset(13, "unexpected.zip")]]

    with pytest.raises(SystemExit, match="exact expected inventory"):
        module.verify_asset_listing_until_complete(
            fetch_extra,
            extra_map_path,
            123,
            expected_names,
            clock=lambda: 0.0,
            sleep=lambda _delay: pytest.fail("unexpected retry for an extra asset"),
            deadline_seconds=5,
            backoff_seconds=2,
        )
    assert extra_calls == 1
    assert not extra_map_path.exists()
    duplicate_id_assets = [
        asset(10, expected_names[0]),
        asset(10, expected_names[1]),
    ]
    with pytest.raises(SystemExit, match="duplicate asset ID"):
        module.asset_map_for_pages([duplicate_id_assets], 123, expected_names)

    timeout_calls: list[float] = []

    def fetch_timeout(timeout: float) -> list[object]:
        timeout_calls.append(timeout)
        raise module.subprocess.TimeoutExpired(["gh", "api"], timeout)

    with pytest.raises(SystemExit, match="exhausted the retry deadline"):
        module.verify_asset_listing_until_complete(
            fetch_timeout,
            tmp_path / "timeout-asset-map.json",
            123,
            expected_names,
            clock=lambda: 0.0,
            sleep=lambda _delay: pytest.fail("unexpected sleep after timeout"),
            deadline_seconds=5,
            backoff_seconds=2,
        )
    assert timeout_calls == [5]
    captured_subprocess_timeout: list[float] = []
    original_run = module.subprocess.run

    def timeout_run(*args, **kwargs):
        captured_subprocess_timeout.append(kwargs["timeout"])
        raise module.subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    module.subprocess.run = timeout_run
    try:
        with pytest.raises(SystemExit, match="exhausted the retry deadline"):
            module.fetch_asset_pages("theHimanshuShekhar/BhayanakLegends", 123, 0.5)
    finally:
        module.subprocess.run = original_run
    assert captured_subprocess_timeout == [0.5]


def test_promotion_rejects_changed_asset_id_before_patch(tmp_path: Path):
    source = _workflow_python(
        "Promote verified release draft",
        marker="          # PROMOTION_ASSET_RECHECK",
    )
    module_path = tmp_path / "promotion_asset_recheck.py"
    module_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("promotion_asset_recheck", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    verified_map = {
        "latest.json": 10,
        "updater.exe": 11,
        "updater.exe.sig": 12,
    }
    verified_map_path = tmp_path / "verified-assets.json"
    verified_map_path.write_text(json.dumps(verified_map) + "\n", encoding="utf-8")
    unchanged_pages = [
        [
            {"id": asset_id, "name": name, "release": {"id": 123}}
            for name, asset_id in verified_map.items()
        ]
    ]
    changed_pages = [
        [
            {"id": 999 if name == "updater.exe" else asset_id, "name": name, "release": {"id": 123}}
            for name, asset_id in verified_map.items()
        ]
    ]

    patch_calls = 0

    def patch_if_verified(pages: list[object]) -> None:
        nonlocal patch_calls
        module.verify_promotion_asset_map(verified_map_path, pages, 123)
        patch_calls += 1

    patch_if_verified(unchanged_pages)
    with pytest.raises(SystemExit, match="changed after verification"):
        patch_if_verified(changed_pages)
    assert patch_calls == 1


def test_workflow_stages_signed_exe_once_and_uploads_unique_assets(tmp_path: Path):
    version = "0.1.13"
    source_name = "Bhayanak Legends_0.1.13_x64-setup.exe"
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


def test_workflow_stages_separate_unsigned_installer_and_signed_archive(
    tmp_path: Path,
):
    version = "0.1.13"
    installer_name = "Bhayanak Legends_0.1.13_x64-setup.exe"
    archive_name = "Bhayanak Legends_0.1.13_x64.nsis.zip"
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
    upload = workflow.index("Upload exact updater and Findings Pack assets to draft")
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
    assert "uv run --project backend --locked python -" in upload_step
    assert "from urllib.request import HTTPRedirectHandler, Request, build_opener" in upload_step
    assert "class RejectRedirectHandler(HTTPRedirectHandler)" in upload_step
    assert "NO_REDIRECT_OPENER = build_opener(RejectRedirectHandler)" in upload_step
    assert "opener=NO_REDIRECT_OPENER.open" in upload_step
    assert "urlopen" not in upload_step
    assert "https://api.github.com/repos/{repository}/releases/{release_id}" in upload_step
    assert "https://uploads.github.com/repos/{repository}/releases/{release_id}/assets" in upload_step
    assert "quote(name, safe='')" in upload_step
    assert "path.is_file()" in upload_step
    assert "remote_assets" in upload_step
    assert "uploaded_ids" in upload_step
    assert 'RUNNER_TEMP_NATIVE="$(cygpath -m "$RUNNER_TEMP_MSYS")"' in upload_step
    assert '"$INVENTORY_PATH_NATIVE"' in upload_step
    assert '"$IDENTITY_PATH_NATIVE"' in upload_step
    assert "ASSET_PATH_CURL" not in upload_step
    assert "--config -" not in upload_step
    assert "curl" not in upload_step
    assert "gh api" not in upload_step
    assert "--method POST" not in upload_step
    assert "gh release upload" not in upload_step
    assert "--clobber" not in upload_step
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
    assert "safe unique updater assets" in workflow

def test_tauri_config_enables_signed_updater_artifacts():
    config = json.loads((REPO_ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))

    assert config["bundle"]["createUpdaterArtifacts"] is True
    assert config["plugins"]["updater"]["endpoints"] == [
        "https://github.com/theHimanshuShekhar/BhayanakLegends/releases/latest/download/latest.json"
    ]
    assert config["plugins"]["updater"]["pubkey"]

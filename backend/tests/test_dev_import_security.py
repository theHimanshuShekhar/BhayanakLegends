import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.import_paths import (
    ImportPathNotApprovedError,
    InvalidImportDirectoryError,
)
from bhayanak_legends.sse import Hub
from bhayanak_legends.store import Store
from bhayanak_legends.sync import SyncService


AUTH = {"X-BL-Token": "dev"}
STATUS = {
    "state": "idle",
    "mode": "import",
    "total_queued": 0,
    "downloaded": 0,
    "skipped": 0,
    "failed": 0,
    "current_match_id": None,
    "started_at": None,
}


def make_app(
    tmp_path: Path,
    *,
    allow_import: bool = True,
    import_roots: list[Path] | None = None,
):
    config = SidecarConfig(
        token="dev",
        data_dir=tmp_path / "data",
        pack_dir=Path(__file__).resolve().parents[2] / "pack",
        allow_import=allow_import,
        import_roots=import_roots or [],
    )
    return create_app(config)


def test_import_settings_parse_explicit_environment_values(tmp_path: Path, monkeypatch):
    root = tmp_path / "approved"
    monkeypatch.setenv("BHAYANAK_ALLOW_IMPORT", "true")
    monkeypatch.setenv("BHAYANAK_IMPORT_ROOTS", json.dumps([str(root)]))

    config = SidecarConfig()

    assert config.allow_import is True
    assert config.import_roots == [root]


def post_import(app, directory: Path):
    with TestClient(app) as client:
        return client.post("/dev/import", json={"dir": str(directory)}, headers=AUTH)


def guard_service(app):
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not read rejected import paths")

    app.state.sync_service.import_from_dir = forbidden
    return lambda: called


def test_import_rejects_directory_outside_approved_root_before_service(tmp_path: Path):
    approved = tmp_path / "approved"
    approved.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    app = make_app(tmp_path, import_roots=[approved])
    was_called = guard_service(app)

    response = post_import(app, outside)

    assert response.status_code == 403
    assert response.json()["detail"] == "import path not approved"
    assert was_called() is False


@pytest.mark.parametrize(
    ("allow_import", "roots"),
    [(False, ["approved"]), (True, [])],
)
def test_import_requires_explicit_flag_and_non_empty_roots(
    tmp_path: Path, allow_import: bool, roots: list[str]
):
    approved = tmp_path / "approved"
    approved.mkdir()
    app = make_app(
        tmp_path,
        allow_import=allow_import,
        import_roots=[tmp_path / root for root in roots],
    )
    was_called = guard_service(app)

    response = post_import(app, approved)

    assert response.status_code == 403
    assert response.json()["detail"] == "dev import disabled"
    assert was_called() is False


def test_import_disables_when_all_configured_roots_are_missing(tmp_path: Path):
    approved = tmp_path / "approved"
    approved.mkdir()
    app = make_app(tmp_path, import_roots=[tmp_path / "missing-root"])
    was_called = guard_service(app)

    response = post_import(app, approved)

    assert response.status_code == 403
    assert response.json()["detail"] == "dev import disabled"
    assert was_called() is False


def test_import_allows_approved_root_itself(tmp_path: Path):
    approved = tmp_path / "approved"
    approved.mkdir()
    app = make_app(tmp_path, import_roots=[approved])
    app.state.sync_service.import_from_dir = lambda directory, loop: STATUS

    response = post_import(app, approved)

    assert response.status_code == 200


def test_import_rejects_frozen_sidecar_even_with_import_settings(tmp_path: Path, monkeypatch):
    approved = tmp_path / "approved"
    approved.mkdir()
    app = make_app(tmp_path, import_roots=[approved])
    was_called = guard_service(app)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    response = post_import(app, approved)

    assert response.status_code == 403
    assert response.json()["detail"] == "dev import disabled"
    assert was_called() is False


@pytest.mark.parametrize("directory_kind", ["missing", "file"])
def test_import_rejects_missing_or_non_directory_before_service(
    tmp_path: Path, directory_kind: str
):
    approved = tmp_path / "approved"
    approved.mkdir()
    directory = tmp_path / directory_kind
    if directory_kind == "file":
        directory.write_text("not a directory")
    app = make_app(tmp_path, import_roots=[approved])
    was_called = guard_service(app)

    response = post_import(app, directory)

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid import directory"
    assert was_called() is False


def test_import_passes_canonical_nested_directory_to_service(tmp_path: Path):
    approved = tmp_path / "approved"
    nested = approved / "nested"
    nested.mkdir(parents=True)
    app = make_app(tmp_path, import_roots=[approved])
    seen: list[Path] = []
    app.state.sync_service.import_from_dir = lambda directory, loop: (
        seen.append(directory) or STATUS
    )

    response = post_import(app, approved / "nested" / ".." / "nested")

    assert response.status_code == 200
    assert seen == [nested.resolve()]


def test_import_allows_symlink_to_approved_directory(tmp_path: Path):
    approved = tmp_path / "approved"
    approved.mkdir()
    link = tmp_path / "approved-link"
    link.symlink_to(approved, target_is_directory=True)
    app = make_app(tmp_path, import_roots=[approved])
    seen: list[Path] = []
    app.state.sync_service.import_from_dir = lambda directory, loop: (
        seen.append(directory) or STATUS
    )

    response = post_import(app, link)

    assert response.status_code == 200
    assert seen == [approved.resolve()]


def test_import_rejects_symlink_escape_and_root_boundary(tmp_path: Path):
    approved = tmp_path / "approved"
    approved.mkdir()
    outside = tmp_path / "approved-other"
    outside.mkdir()
    escaped = approved / "escaped"
    escaped.symlink_to(outside, target_is_directory=True)
    app = make_app(tmp_path, import_roots=[approved])
    was_called = guard_service(app)

    escaped_response = post_import(app, escaped)
    boundary_response = post_import(app, outside)

    assert escaped_response.status_code == 403
    assert escaped_response.json()["detail"] == "import path not approved"
    assert boundary_response.status_code == 403
    assert boundary_response.json()["detail"] == "import path not approved"
    assert was_called() is False


def test_sync_service_rejects_outside_path_before_fetch_state_read(tmp_path: Path):
    approved = tmp_path / "approved"
    approved.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    service = SyncService(
        Store(tmp_path / "app.db"), Hub(), lambda: {}, import_roots=[approved]
    )

    with pytest.raises(ImportPathNotApprovedError, match="import path not approved"):
        service.import_from_dir(outside)


def test_sync_service_rejects_missing_directory_before_fetch_state_read(tmp_path: Path):
    approved = tmp_path / "approved"
    approved.mkdir()
    service = SyncService(
        Store(tmp_path / "app.db"), Hub(), lambda: {}, import_roots=[approved]
    )

    with pytest.raises(InvalidImportDirectoryError, match="invalid import directory"):
        service.import_from_dir(tmp_path / "missing")


def test_sync_service_fails_closed_when_approved_root_is_missing(tmp_path: Path):
    service = SyncService(
        Store(tmp_path / "app.db"),
        Hub(),
        lambda: {},
        import_roots=[tmp_path / "missing-root"],
    )

    with pytest.raises(ImportPathNotApprovedError, match="import path not approved"):
        service.import_from_dir(tmp_path)

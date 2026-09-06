from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "backend" / "tools" / "history_purge.py"
CHECK_PII = ROOT / "backend" / "tools" / "check_pii.py"


def load_tool(path: Path, name: str = "history_purge_test"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve postponed annotations through sys.modules while the
    # dynamically loaded tool is being collected.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PURGE = load_tool(TOOL)


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def commit(root: Path, message: str) -> None:
    git(root, "add", ".")
    git(root, "commit", "-qm", message)


def fixture(path: Path, puuid: str, score: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "metadata": {"participants": [puuid]},
                "info": {"participants": [{"puuid": puuid, "score": score}]},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def make_repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "main")
    git(repository, "config", "user.name", "Purge Test")
    git(repository, "config", "user.email", "purge-test@example.invalid")
    first = "leaked-puuid-alpha"
    second = "leaked-puuid-beta"
    fixture(repository / "backend/tests/fixtures/base.json", first, 7)
    commit(repository, "base fixture")
    git(repository, "switch", "-q", "-c", "alternate")
    fixture(repository / "backend/tests/fixtures/secondary.json", second, 11)
    commit(repository, "alternate fixture")
    git(repository, "tag", "release-fixtures")
    git(repository, "switch", "-q", "main")
    # A remote-tracking ref exercises the origin-only reachability helper
    # without contacting a remote.
    main_commit = git(repository, "rev-parse", "main").stdout.strip()
    git(repository, "update-ref", "refs/remotes/origin/main", main_commit)
    return repository, first, second


def snapshot_refs(root: Path) -> dict[str, str]:
    lines = git(root, "for-each-ref", "--format=%(refname)=%(objectname)").stdout.splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_apply_without_owner_comment_fails_before_ref_or_remote_contact(tmp_path: Path):
    repository, first, _ = make_repository(tmp_path)
    before = snapshot_refs(repository)
    sentinel = tmp_path / "remote-contacted"
    ssh = tmp_path / "ssh-sentinel"
    ssh.write_text(f"#!/bin/sh\ntouch {sentinel}\nexit 1\n", encoding="utf-8")
    ssh.chmod(0o700)
    git(repository, "remote", "add", "origin", "ssh://example.invalid/owner/repository")
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--apply",
            "--root",
            str(repository),
            "--map-path",
            str(tmp_path / "map.txt"),
            "--backup-dir",
            str(tmp_path / "backup"),
            "--expected-inventory-count",
            "2",
            "--backup-reviewed",
            "--authorization",
            PURGE.AUTHORIZATION,
        ],
        cwd=ROOT,
        env={**os.environ, "GIT_SSH_COMMAND": str(ssh)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert snapshot_refs(repository) == before
    assert not sentinel.exists()
    assert first not in result.stdout
    assert first not in result.stderr


def test_dry_run_inventory_is_external_deterministic_and_non_mutating(tmp_path: Path):
    repository, first, second = make_repository(tmp_path)
    before = PURGE.snapshot_repository(repository)
    map_one = tmp_path / "map-one.txt"
    map_two = tmp_path / "map-two.txt"
    inventory = PURGE.inventory_repository(repository)
    assert inventory.count == 2
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--dry-run",
            "--root",
            str(repository),
            "--map-path",
            str(map_one),
            "--expected-inventory-count",
            str(inventory.count),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert map_one.is_file()
    assert PURGE.snapshot_repository(repository) == before
    assert first not in result.stdout and second not in result.stdout
    assert "refs_unchanged" in result.stdout

    PURGE.write_replacement_map(map_two, inventory, before, repository_root=repository)
    assert map_one.read_bytes() == map_two.read_bytes()
    parsed = PURGE.load_replacement_map(map_one, expected_count=inventory.count)
    assert parsed.inventory_count == 2
    assert {source for source, _ in parsed.entries} == {first, second}


def test_dry_run_rejects_map_inside_repository(tmp_path: Path):
    repository, _, _ = make_repository(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--dry-run",
            "--root",
            str(repository),
            "--map-path",
            str(repository / "replacement-map.txt"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not (repository / "replacement-map.txt").exists()


def test_preflight_rejects_count_or_backup_mismatch_before_authorization_lookup(tmp_path: Path, monkeypatch):
    repository, _, _ = make_repository(tmp_path)
    inventory = PURGE.inventory_repository(repository)
    snapshot = PURGE.snapshot_repository(repository)
    map_path = tmp_path / "replacement-map.txt"
    PURGE.write_replacement_map(map_path, inventory, snapshot, repository_root=repository)
    backup_dir = tmp_path / "backup"
    PURGE.create_backup(repository, backup_dir, snapshot=snapshot)
    looked_up: list[str] = []
    monkeypatch.setattr(PURGE, "_fetch_authorization_comment", lambda value: looked_up.append(value))

    with pytest.raises(PURGE.PurgeError, match="inventory count"):
        PURGE.preflight_apply(
            repository,
            map_path,
            backup_dir,
            authorization_comment_id="12345",
            expected_count=inventory.count + 1,
            backup_reviewed=True,
        )
    assert looked_up == []

    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["snapshot"]["object_count"] += 1
    (backup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PURGE.PurgeError):
        PURGE.preflight_apply(
            repository,
            map_path,
            backup_dir,
            authorization_comment_id="12345",
            expected_count=inventory.count,
            backup_reviewed=True,
        )
    assert looked_up == []


def comment_payload(comment_id: str = "12345", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": int(comment_id),
        "issue_url": "https://api.github.com/repos/theHimanshuShekhar/BhayanakLegends/issues/59",
        "html_url": f"https://github.com/theHimanshuShekhar/BhayanakLegends/issues/59#issuecomment-{comment_id}",
        "user": {"login": "theHimanshuShekhar"},
        "author_association": "OWNER",
        "body": PURGE.AUTHORIZATION,
    }
    payload.update(overrides)
    return payload


def test_authorization_requires_verified_owner_comment_and_exact_body():
    calls: list[str] = []

    def fetch(comment_id: str) -> dict[str, Any]:
        calls.append(comment_id)
        return comment_payload(comment_id)

    assert PURGE.authorization_matches(comment_id="12345", fetcher=fetch)
    assert PURGE.authorization_matches(
        comment_url="https://github.com/theHimanshuShekhar/BhayanakLegends/issues/59#issuecomment-12345",
        fetcher=fetch,
    )
    assert calls == ["12345", "12345"]
    assert not PURGE.authorization_matches(PURGE.AUTHORIZATION, fetcher=fetch)
    assert not PURGE.authorization_matches(
        comment_id="12345",
        fetcher=lambda _: comment_payload(body=f"quoted: {PURGE.AUTHORIZATION}"),
    )
    assert not PURGE.authorization_matches(
        comment_id="12345",
        fetcher=lambda _: comment_payload(user={"login": "not-the-owner"}),
    )
    assert not PURGE.authorization_matches(
        comment_id="12345",
        fetcher=lambda _: comment_payload(author_association="COLLABORATOR"),
    )


def test_locator_record_only_supplies_comment_locator(tmp_path: Path):
    record = tmp_path / "authorization-locator.json"
    record.write_text(
        json.dumps(
            {
                "version": PURGE.AUTHORIZATION_RECORD_VERSION,
                "comment_id": "12345",
                # Spoofable local author/body claims are deliberately ignored.
                "author": "not-the-owner",
                "body": PURGE.AUTHORIZATION,
            }
        ),
        encoding="utf-8",
    )
    payloads: list[str] = []

    def fetch(comment_id: str) -> dict[str, Any]:
        payloads.append(comment_id)
        return comment_payload(comment_id)

    assert PURGE.authorization_matches(path=record, fetcher=fetch)
    assert payloads == ["12345"]


def make_rewritten_repository(tmp_path: Path, first: str, second: str) -> Path:
    rewritten = tmp_path / "rewritten"
    rewritten.mkdir()
    git(rewritten, "init", "-q", "-b", "main")
    git(rewritten, "config", "user.name", "Purge Test")
    git(rewritten, "config", "user.email", "purge-test@example.invalid")
    fixture(rewritten / "backend/tests/fixtures/base.json", "fixture-puuid-01", 7)
    commit(rewritten, "rewritten base fixture")
    git(rewritten, "switch", "-q", "-c", "alternate")
    fixture(rewritten / "backend/tests/fixtures/secondary.json", "fixture-puuid-02", 11)
    commit(rewritten, "rewritten alternate fixture")
    git(rewritten, "tag", "release-fixtures")
    main_commit = git(rewritten, "rev-parse", "main").stdout.strip()
    git(rewritten, "update-ref", "refs/remotes/origin/main", main_commit)
    return rewritten


def test_post_rewrite_verification_checks_guard_reachability_and_projection(tmp_path: Path):
    original, first, second = make_repository(tmp_path)
    snapshot = PURGE.snapshot_repository(original)
    backup = tmp_path / "backup"
    PURGE.create_backup(original, backup, snapshot=snapshot)
    rewritten = make_rewritten_repository(tmp_path, first, second)

    result = PURGE.verify_post_rewrite(
        rewritten,
        backup / "mirror",
        snapshot.commit_ids,
        check_pii_path=CHECK_PII,
    )
    assert result.history_guard_passed
    assert result.original_commits_reachable == ()
    assert result.fixture_projection_equal

    git(rewritten, "switch", "-q", "alternate")
    fixture(rewritten / "backend/tests/fixtures/secondary.json", "fixture-puuid-02", 999)
    commit(rewritten, "semantic drift")
    assert not PURGE.compare_fixture_projections(backup / "mirror", rewritten)

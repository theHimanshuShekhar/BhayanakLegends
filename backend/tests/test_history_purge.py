from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
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


def test_filter_repo_changes_every_reachable_commit_oid(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "main")
    git(repository, "config", "user.name", "Purge Test")
    git(repository, "config", "user.email", "purge-test@example.invalid")
    (repository / "README").write_text("identity-free history\n", encoding="utf-8")
    commit(repository, "identity-free root")
    fixture(repository / "backend/tests/fixtures/base.json", "leaked-puuid-alpha", 7)
    commit(repository, "add fixture")
    before = PURGE.snapshot_repository(repository)
    inventory = PURGE.inventory_repository(repository)
    map_path = tmp_path / "replacement-map.txt"
    replacement = PURGE.write_replacement_map(
        map_path,
        inventory,
        before,
        repository_root=repository,
    )
    plan = PURGE.ApplyPlan(
        repository,
        map_path,
        tmp_path / "backup",
        before,
        replacement,
        True,
        PURGE.public_ref_manifest(repository),
    )

    PURGE._run_filter_repo(plan)

    assert PURGE.reachable_origin_commits(repository).isdisjoint(before.commit_ids)


def test_fixture_projection_permits_only_reviewed_identity_replacements(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    for repository in (before, after):
        repository.mkdir()
        git(repository, "init", "-q", "-b", "main")
        git(repository, "config", "user.name", "Purge Test")
        git(repository, "config", "user.email", "purge-test@example.invalid")
    fixture_path = Path("backend/tests/fixtures/collision.json")
    (before / fixture_path).parent.mkdir(parents=True)
    (after / fixture_path).parent.mkdir(parents=True)
    (before / fixture_path).write_text(
        json.dumps({"summonerName": "LeakedPlayer", "team": "LeakedPlayer", "score": 7}),
        encoding="utf-8",
    )
    (after / fixture_path).write_text(
        json.dumps({"summonerName": "FixturePlayer01", "team": "FixturePlayer01", "score": 7}),
        encoding="utf-8",
    )
    commit(before, "before")
    commit(after, "after")

    replacements = (("LeakedPlayer", "FixturePlayer01"),)
    assert not PURGE.compare_fixture_projections(before, after)
    assert PURGE.compare_fixture_projections(before, after, replacements=replacements)

    (after / fixture_path).write_text(
        json.dumps({"summonerName": "FixturePlayer01", "team": "FixturePlayer01", "score": 8}),
        encoding="utf-8",
    )
    git(after, "add", ".")
    git(after, "commit", "--amend", "-qm", "after")
    assert not PURGE.compare_fixture_projections(before, after, replacements=replacements)


def test_replacement_ordinals_reserve_participant_linked_targets() -> None:
    puuid = "source-puuid-value"
    linked_name = "related-player-name"
    standalone_name = "a-standalone-name"
    inventory = PURGE.Inventory(
        occurrences=(),
        values=tuple(sorted((puuid, linked_name, standalone_name), key=lambda value: value.encode())),
        categories={
            puuid: frozenset({"puuid"}),
            linked_name: frozenset({"riot_name"}),
            standalone_name: frozenset({"name"}),
        },
        relations={linked_name: puuid},
    )

    replacements = dict(PURGE._replacement_entries(inventory))

    assert replacements[linked_name] == "FixturePlayer01"
    assert replacements[standalone_name] == "FixturePlayer02"
    assert len(set(replacements.values())) == len(replacements)


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


def comment_payload(comment_id: str = PURGE.AUTHORIZED_COMMENT_ID, **overrides: Any) -> dict[str, Any]:
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

    comment_id = PURGE.AUTHORIZED_COMMENT_ID
    assert PURGE.authorization_matches(comment_id=comment_id, fetcher=fetch)
    assert PURGE.authorization_matches(
        comment_url=f"https://github.com/theHimanshuShekhar/BhayanakLegends/issues/59#issuecomment-{comment_id}",
        fetcher=fetch,
    )
    assert calls == [comment_id, comment_id]
    assert not PURGE.authorization_matches(PURGE.AUTHORIZATION, fetcher=fetch)
    assert not PURGE.authorization_matches(
        comment_id=comment_id,
        fetcher=lambda _: comment_payload(body=f"quoted: {PURGE.AUTHORIZATION}"),
    )
    assert not PURGE.authorization_matches(
        comment_id=comment_id,
        fetcher=lambda _: comment_payload(user={"login": "not-the-owner"}),
    )
    assert not PURGE.authorization_matches(
        comment_id=comment_id,
        fetcher=lambda _: comment_payload(author_association="COLLABORATOR"),
    )
    assert not PURGE.authorization_matches(comment_id="12345", fetcher=fetch)


def test_locator_record_only_supplies_comment_locator(tmp_path: Path):
    record = tmp_path / "authorization-locator.json"
    record.write_text(
        json.dumps(
            {
                "version": PURGE.AUTHORIZATION_RECORD_VERSION,
                "comment_id": PURGE.AUTHORIZED_COMMENT_ID,
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
    assert payloads == [PURGE.AUTHORIZED_COMMENT_ID]


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
    verification = PURGE.create_verification_mirror(rewritten, tmp_path / "verification")

    result = PURGE.verify_post_rewrite(
        verification,
        backup / "mirror",
        snapshot.commit_ids,
        check_pii_path=CHECK_PII,
    )
    assert result.history_guard_passed
    assert result.original_commits_reachable == ()
    assert result.fixture_projection_equal
    assert result.public_refs_manifest_equal

    git(rewritten, "switch", "-q", "alternate")
    fixture(rewritten / "backend/tests/fixtures/secondary.json", "fixture-puuid-02", 999)
    commit(rewritten, "semantic drift")
    assert not PURGE.compare_fixture_projections(backup / "mirror", rewritten)


def test_public_ref_verification_rejects_empty_missing_and_unexpected_refs(tmp_path: Path):
    original, first, second = make_repository(tmp_path)
    snapshot = PURGE.snapshot_repository(original)
    backup = tmp_path / "backup"
    PURGE.create_backup(original, backup, snapshot=snapshot)
    rewritten = make_rewritten_repository(tmp_path, first, second)
    expected = PURGE.public_ref_manifest(rewritten)

    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "-q", "--bare")
    with pytest.raises(PURGE.PurgeError, match="manifest is empty"):
        PURGE.public_ref_manifest(empty)

    missing = PURGE.create_verification_mirror(rewritten, tmp_path / "missing")
    git(missing, "update-ref", "-d", "refs/tags/release-fixtures")
    with pytest.raises(PURGE.PurgeError, match="manifest changed"):
        PURGE.verify_post_rewrite(
            missing,
            backup / "mirror",
            snapshot.commit_ids,
            check_pii_path=CHECK_PII,
            expected_public_refs=expected,
        )

    unexpected = PURGE.create_verification_mirror(rewritten, tmp_path / "unexpected")
    main_commit = git(unexpected, "rev-parse", "refs/heads/main").stdout.strip()
    git(unexpected, "update-ref", "refs/tags/unexpected", main_commit)
    with pytest.raises(PURGE.PurgeError, match="manifest changed"):
        PURGE.verify_post_rewrite(
            unexpected,
            backup / "mirror",
            snapshot.commit_ids,
            check_pii_path=CHECK_PII,
            expected_public_refs=expected,
        )


def test_verification_mirror_is_new_and_external(tmp_path: Path):
    repository, first, second = make_repository(tmp_path)
    rewritten = make_rewritten_repository(tmp_path, first, second)
    destination = PURGE.create_verification_mirror(rewritten, tmp_path / "verification")
    assert destination.is_dir()
    assert PURGE.public_ref_manifest(destination)
    with pytest.raises(PURGE.PurgeError, match="new path"):
        PURGE.create_verification_mirror(rewritten, destination)
    with pytest.raises(PURGE.PurgeError, match="outside the repository"):
        PURGE.create_verification_mirror(rewritten, rewritten / "nested-verification")


def test_apply_requires_all_fresh_verification_gates(tmp_path: Path, capsys):
    repository, _, _ = make_repository(tmp_path)
    common = [
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
    ]
    options = {
        "verification_repo": ["--verification-repo", str(tmp_path / "verification")],
        "check_pii": ["--check-pii", str(CHECK_PII)],
        "evidence_path": ["--evidence-path", str(tmp_path / "evidence.json")],
    }
    for missing in options:
        argv = common + [
            argument
            for name, values in options.items()
            if name != missing
            for argument in values
        ]
        assert PURGE.main(argv) == 2
        assert "requires" in capsys.readouterr().err


def test_apply_evidence_records_inventory_count(tmp_path: Path, monkeypatch):
    original, _, _ = make_repository(tmp_path)
    candidate = PURGE.create_verification_mirror(original, tmp_path / "candidate")
    snapshot = PURGE.snapshot_repository(candidate)
    backup_dir = tmp_path / "backup"
    PURGE.create_backup(candidate, backup_dir, snapshot=snapshot)
    inventory = PURGE.inventory_repository(original)
    map_path = tmp_path / "map.txt"
    replacement = PURGE.write_replacement_map(
        map_path,
        inventory,
        snapshot,
        repository_root=candidate,
    )
    plan = PURGE.ApplyPlan(
        candidate,
        map_path,
        backup_dir,
        snapshot,
        replacement,
        True,
        PURGE.public_ref_manifest(candidate),
    )
    monkeypatch.setattr(PURGE, "preflight_apply", lambda *args, **kwargs: plan)
    monkeypatch.setattr(PURGE, "_run_filter_repo", lambda _plan: None)
    monkeypatch.setattr(
        PURGE,
        "verify_post_rewrite",
        lambda *args, **kwargs: PURGE.VerificationResult(True, (), True, True),
    )
    evidence_path = tmp_path / "evidence.json"
    args = SimpleNamespace(
        map_path=map_path,
        backup_dir=backup_dir,
        verification_repo=tmp_path / "verification-output",
        check_pii=CHECK_PII,
        evidence_path=evidence_path,
        authorization=None,
        authorization_file=None,
        authorization_comment_id=None,
        authorization_comment_url=None,
        expected_inventory_count=replacement.inventory_count,
        backup_reviewed=True,
    )
    assert PURGE._apply(args, candidate) == 0
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))


def _finalization_evidence(
    repository: Path,
    map_path: Path,
    snapshot: PURGE.RepositorySnapshot,
    *,
    checklist: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pre_manifest = [
        list(item)
        for item in snapshot.refs
        if item[0].startswith("refs/heads/") or item[0].startswith("refs/tags/")
    ]
    candidate_verification = PURGE.create_verification_mirror(
        repository,
        repository.parent / "apply-verification",
    )
    post_manifest = [list(item) for item in PURGE.public_ref_manifest(candidate_verification)]
    checker_digest = PURGE.hashlib.sha256(CHECK_PII.read_bytes()).hexdigest()
    verification = {
        "computed": True,
        "computed_by": "history_purge.apply",
        "provenance": "candidate-local-external-mirror",
        "fresh_clone": True,
        "verification_repo_kind": "full-mirror",
        "verification_repo": str(candidate_verification),
        "history_guard_passed": True,
        "original_commits_reachable": [],
        "fixture_projection_equal": True,
        "public_refs_manifest_equal": True,
        "public_ref_manifest": post_manifest,
    }
    return {
        "version": PURGE.EVIDENCE_VERSION,
        "mode": "apply-local-only",
        "pre_rewrite_snapshot": PURGE._snapshot_payload(snapshot),
        "post_rewrite_snapshot": PURGE._snapshot_payload(snapshot),
        "pre_rewrite_public_ref_manifest": pre_manifest,
        "post_rewrite_public_ref_manifest": post_manifest,
        "replacement_map_path": str(map_path),
        "replacement_inventory_count": PURGE.load_replacement_map(map_path).inventory_count,
        "replacement_map_sha256": PURGE.load_replacement_map(map_path).map_sha256,
        "backup_reviewed": True,
        "backup_dir": str(repository.parent / "evidence-backup"),
        "check_pii_path": str(CHECK_PII.resolve()),
        "check_pii_sha256": checker_digest,
        "verification_repo": str(candidate_verification),
        "verification_repo_kind": "full-mirror",
        "remote_contacted": False,
        "force_push_performed": True,
        "verification": verification,
        "post_push_verification": None,
        "checklist": checklist or [
            {
                **item,
                "status": (
                    "owner-required"
                    if item["id"] == "securely_delete_external_map"
                    else "completed"
                ),
                **(
                    {}
                    if item["id"] == "securely_delete_external_map"
                    else {"evidence": "synthetic owner evidence"}
                ),
            }
            for item in PURGE.post_rewrite_checklist()
        ],
        "external_map_deleted": False,
    }


def _run_verify_origin_for_test(
    candidate: Path,
    evidence_path: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = PURGE.create_verification_mirror(candidate, tmp_path / "origin-source")
    real_run = PURGE._run_command
    commands: list[list[str]] = []

    def fake_run(command, *, cwd=None, input_data=None):
        commands.append(list(command))
        if (
            len(command) >= 5
            and list(command[:3]) == ["git", "clone", "--mirror"]
            and command[3] == PURGE.CANONICAL_ORIGIN_URL
        ):
            mapped = list(command)
            mapped[3] = str(source)
            result = real_run(mapped, cwd=cwd, input_data=input_data)
            real_run(
                [
                    "git",
                    "-C",
                    command[4],
                    "config",
                    "remote.origin.url",
                    PURGE.CANONICAL_ORIGIN_URL,
                ]
            )
            return result
        return real_run(command, cwd=cwd, input_data=input_data)

    monkeypatch.setattr(PURGE, "_run_command", fake_run)
    monkeypatch.setattr(
        PURGE,
        "_fetch_authorization_comment",
        lambda comment_id: comment_payload(comment_id),
    )
    assert PURGE.main(
        [
            "--verify-origin",
            "--root",
            str(candidate),
            "--verification-repo",
            str(tmp_path / "canonical-verification"),
            "--evidence-path",
            str(evidence_path),
            "--authorization-comment-id",
            PURGE.AUTHORIZED_COMMENT_ID,
        ]
    ) == 0
    assert any(
        command[:4] == ["git", "clone", "--mirror", PURGE.CANONICAL_ORIGIN_URL]
        for command in commands
    )


def test_finalize_refuses_incomplete_checklist(tmp_path: Path, monkeypatch):
    original, first, second = make_repository(tmp_path)
    snapshot = PURGE.snapshot_repository(original)
    backup_dir = tmp_path / "evidence-backup"
    PURGE.create_backup(original, backup_dir, snapshot=snapshot)
    rewritten = make_rewritten_repository(tmp_path, first, second)
    candidate = PURGE.create_verification_mirror(rewritten, tmp_path / "candidate")
    inventory = PURGE.inventory_repository(original)
    map_path = tmp_path / "map.txt"
    replacement = PURGE.write_replacement_map(
        map_path,
        inventory,
        snapshot,
        repository_root=candidate,
    )
    checklist = PURGE.post_rewrite_checklist()
    checklist[0]["status"] = "owner-required"
    checklist[0]["evidence"] = ""
    evidence_path = tmp_path / "evidence.json"
    evidence = _finalization_evidence(candidate, map_path, snapshot, checklist=checklist)
    PURGE.write_evidence_record(evidence_path, evidence, root=candidate)
    _run_verify_origin_for_test(candidate, evidence_path, tmp_path, monkeypatch)
    with pytest.raises(PURGE.PurgeError, match="checklist item"):
        PURGE.finalize_map_deletion(candidate, map_path, evidence_path)
    assert map_path.is_file()
    assert replacement.map_sha256 == PURGE.load_replacement_map(map_path).map_sha256


def test_finalize_map_deletion_updates_evidence_and_deletes_map(tmp_path: Path, monkeypatch):
    original, first, second = make_repository(tmp_path)
    snapshot = PURGE.snapshot_repository(original)
    backup_dir = tmp_path / "evidence-backup"
    PURGE.create_backup(original, backup_dir, snapshot=snapshot)
    rewritten = make_rewritten_repository(tmp_path, first, second)
    candidate = PURGE.create_verification_mirror(rewritten, tmp_path / "candidate")
    inventory = PURGE.inventory_repository(original)
    map_path = tmp_path / "map.txt"
    PURGE.write_replacement_map(
        map_path,
        inventory,
        snapshot,
        repository_root=candidate,
    )
    evidence_path = tmp_path / "evidence.json"
    evidence = _finalization_evidence(candidate, map_path, snapshot)
    PURGE.write_evidence_record(evidence_path, evidence, root=candidate)
    _run_verify_origin_for_test(candidate, evidence_path, tmp_path, monkeypatch)

    assert PURGE.main(
        [
            "--finalize-map-deletion",
            "--root",
            str(candidate),
            "--map-path",
            str(map_path),
            "--evidence-path",
            str(evidence_path),
        ]
    ) == 0
    assert not map_path.exists()
    updated = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert updated["external_map_deleted"] is True
    map_item = next(
        item for item in updated["checklist"] if item["id"] == "securely_delete_external_map"
    )
    assert map_item["status"] == "completed"

#!/usr/bin/env python3
"""Prepare and verify an owner-run Riot-identity history purge.

The utility is deliberately Git-local.  A dry run inventories reachable Git
blobs and writes a git-filter-repo replacement map to an explicitly selected
location outside the repository.  Apply mode performs only a guarded local
rewrite after checking the exact owner authorization, map, and backup
preconditions; it never contacts a Git remote, force-pushes, sends a
notification, or claims that independently controlled forks were cleaned up.
Map deletion is a separate finalize mode that requires owner evidence for the
candidate and canonical-origin verification gates and every external action.
The one exception is a bounded, read-only GitHub API lookup that validates an
explicit owner-authored issue-comment locator after local preflight.  A copied
issue description or caller-supplied authorization sentence is never enough.

The replacement map necessarily contains source identity values.  The map and
backup are therefore treated as sensitive, external artifacts with restrictive
permissions.  Output contains only paths, fields, counts, and SHA-256
fingerprints.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

AUTHORIZATION = (
    "AUTHORIZED: rewrite all public BhayanakLegends branches and tags to purge "
    "Riot identities and force-push replacements."
)
# The issue body is not authorization.  Apply accepts only a validated
# owner-authored GitHub issue-comment locator.
AUTHORIZED_OWNER = "theHimanshuShekhar"
AUTHORIZED_REPOSITORY = "theHimanshuShekhar/BhayanakLegends"
AUTHORIZED_COMMENT_ID = "5625546905"
AUTHORIZATION_ISSUE = 59
AUTHORIZATION_RECORD_VERSION = "bhayanak-history-purge-authorization-v1"
AUTHORIZATION_API_TIMEOUT = 5.0
# Public aliases make the owner gate unambiguous to callers and tests.
REQUIRED_AUTHORIZATION = AUTHORIZATION
EXACT_AUTHORIZATION = AUTHORIZATION
MAP_VERSION = "bhayanak-history-purge-v1"
CANONICAL_ORIGIN_URL = "git@github.com:theHimanshuShekhar/BhayanakLegends.git"
CANONICAL_ORIGIN_URLS = frozenset(
    {
        "https://github.com/theHimanshuShekhar/BhayanakLegends",
        "git@github.com:theHimanshuShekhar/BhayanakLegends",
        "ssh://git@github.com/theHimanshuShekhar/BhayanakLegends",
    }
)
BACKUP_VERSION = "bhayanak-history-purge-backup-v1"
EVIDENCE_VERSION = "bhayanak-history-purge-evidence-v1"
REPO_ROOT = Path(__file__).resolve().parents[2]

# These are the identity-bearing fields consumed by check_pii.py.  Field names
# are intentionally kept here rather than importing implementation details from
# the tracked-tree guard so this procedure remains usable from a fresh mirror.
FIELD_CATEGORIES: Mapping[str, str] = {
    "puuid": "puuid",
    "summonerId": "summoner_id",
    "riotIdGameName": "riot_name",
    "riotIdTagline": "riot_tag",
    "summonerName": "name",
    "KillerName": "name",
    "VictimName": "name",
    "Assisting": "name",
    "riot_id": "riot_id",
    "riotId": "riot_id",
}
IDENTITY_FIELDS = frozenset(FIELD_CATEGORIES)

_SYNTHETIC_PATTERNS = (
    re.compile(r"(?:fixture|parity)-puuid-[0-9]{2,}\Z"),
    re.compile(r"fixture-summoner-[0-9]{2,}\Z"),
    re.compile(r"FixturePlayer[0-9]{2,}\Z"),
    re.compile(r"BL[0-9]{2,}\Z"),
    re.compile(r"FixturePlayer[0-9]{2,}#BL[0-9]{2,}\Z"),
    re.compile(r"fixture-identity-[0-9]{2,}\Z"),
)
_TEXT_CANDIDATE = re.compile(r"[A-Za-z0-9_#-]{4,}(?: [A-Za-z0-9_#-]+)?")
_QUOTED_CANDIDATE = re.compile(r'''([\"'])(.*?)\1''', re.DOTALL)


class PurgeError(RuntimeError):
    """A fail-closed precondition or verification failure."""


@dataclass(frozen=True)
class Blob:
    object_id: str
    path: str
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class IdentityOccurrence:
    path: str
    field: str
    digest: str
    # Source values stay in memory only until the external map is written.
    value: str = field(repr=False)
    category: str = field(default="generic", repr=False)


@dataclass(frozen=True)
class Inventory:
    occurrences: tuple[IdentityOccurrence, ...]
    values: tuple[str, ...] = field(repr=False)
    categories: Mapping[str, frozenset[str]] = field(repr=False, default_factory=dict)
    relations: Mapping[str, str] = field(repr=False, default_factory=dict)

    @property
    def count(self) -> int:
        """Return the deterministic count of unique source values."""
        return len(self.values)


@dataclass(frozen=True)
class ReplacementMap:
    entries: tuple[tuple[str, str], ...] = field(repr=False)
    inventory_count: int
    snapshot_sha256: str
    map_sha256: str


@dataclass(frozen=True)
class RepositorySnapshot:
    refs: tuple[tuple[str, str], ...]
    object_count: int
    object_manifest_sha256: str
    commit_ids: tuple[str, ...] = field(repr=False)
    archive_checksums: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ApplyPlan:
    root: Path
    map_path: Path
    backup_dir: Path
    snapshot: RepositorySnapshot
    replacement_map: ReplacementMap
    backup_reviewed: bool
    public_ref_manifest: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    history_guard_passed: bool
    original_commits_reachable: tuple[str, ...]
    fixture_projection_equal: bool
    public_refs_manifest_equal: bool = False


POST_REWRITE_CHECKLIST: tuple[tuple[str, str], ...] = (
    (
        "force_update_origin_refs",
        "Atomically force-update every recorded public branch and tag ref after review.",
    ),
    (
        "regenerate_source_archives_and_releases",
        "Regenerate affected GitHub source archives and release assets after review.",
    ),
    (
        "request_github_support_cache_removal",
        "Record a GitHub Support request for cached sensitive diffs/objects; no API call is made here.",
    ),
    (
        "notify_collaborators_to_reclone",
        "Notify known collaborators to discard old clones and re-clone; no messages are sent here.",
    ),
    (
        "notify_known_fork_owners",
        "Notify known third-party fork owners; origin cannot erase independently controlled forks.",
    ),
    (
        "fresh_clone_history_guard",
        "From a fresh clone, run python tools/check_pii.py --history and retain its fingerprint-only result.",
    ),
    (
        "verify_original_commits_unreachable",
        "Verify every pre-rewrite commit is unreachable from origin branch/tag refs.",
    ),
    (
        "compare_non_identity_fixture_projection",
        "Compare fixture projections with the backup and investigate every semantic difference.",
    ),
    (
        "securely_delete_external_map",
        "Securely delete the external map only after the complete evidence record is written.",
    ),
)

_MAP_DELETION_CHECKLIST_ID = "securely_delete_external_map"
_NON_OPTIONAL_CHECKLIST_IDS = frozenset(
    {
        "force_update_origin_refs",
        "regenerate_source_archives_and_releases",
        "request_github_support_cache_removal",
        "fresh_clone_history_guard",
        "verify_original_commits_unreachable",
        "compare_non_identity_fixture_projection",
    }
)



def fingerprint(value: str) -> str:
    """Return the non-reversible digest used by reports."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    input_data: bytes | None = None,
) -> bytes:
    """Run a local command without exposing captured command output."""
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        # Never include stderr: Git can echo paths or content supplied by a
        # caller, and this tool's output contract is fingerprint-only.
        name = Path(command[0]).name if command else "command"
        raise PurgeError(f"local {name} operation failed") from exc
    return result.stdout


def _git(root: Path, *args: str, input_data: bytes | None = None) -> bytes:
    return _run_command(["git", "-C", str(root), *args], input_data=input_data)


def _resolve_path(path: Path | str, *, base: Path | None = None) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (base or Path.cwd()) / candidate
    return candidate


def _repository_root(path: Path | str) -> Path:
    candidate = _resolve_path(path).resolve()
    if not candidate.exists():
        raise PurgeError("repository does not exist")
    try:
        shown = _git(candidate, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    except PurgeError:
        # Bare mirrors have no worktree.  A successful --git-dir probe is
        # enough to establish the local repository seam.
        _git(candidate, "rev-parse", "--git-dir")
        return candidate
    return Path(shown).resolve() if shown else candidate


def _ensure_external_path(root: Path, path: Path | str, kind: str) -> Path:
    """Resolve and validate a file/directory destination outside ``root``."""
    root_real = root.resolve()
    candidate = _resolve_path(path)
    if candidate.is_symlink():
        raise PurgeError(f"{kind} must not be a symlink")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root_real)
    except ValueError:
        pass
    else:
        raise PurgeError(f"{kind} must be outside the repository")
    if resolved == root_real:
        raise PurgeError(f"{kind} must be outside the repository")
    if not resolved.parent.exists() or not resolved.parent.is_dir():
        raise PurgeError(f"{kind} parent directory does not exist")
    return resolved
def _ensure_new_external_path(root: Path, path: Path | str, kind: str) -> Path:
    """Resolve an external destination that must not exist yet."""
    destination = _ensure_external_path(root, path, kind)
    if destination.exists():
        raise PurgeError(f"{kind} must be a new path")
    return destination


def _public_ref_entries(root: Path | str) -> tuple[tuple[str, str], ...]:
    """Return the exact public heads/tags ref manifest, failing when empty."""
    repository = _repository_root(root)
    entries = tuple(
        (name, object_id)
        for name, object_id in _read_refs(repository)
        if name.startswith("refs/heads/") or name.startswith("refs/tags/")
    )
    if not entries:
        raise PurgeError("public heads/tags ref manifest is empty")
    return entries


def public_ref_manifest(root: Path | str) -> tuple[tuple[str, str], ...]:
    """Return the exact nonempty public heads/tags ref-to-OID manifest."""
    return _public_ref_entries(root)


def public_ref_names(root: Path | str) -> tuple[str, ...]:
    """Return public heads/tags names while enforcing a nonempty manifest."""
    return tuple(name for name, _ in _public_ref_entries(root))


def _normalize_public_ref_manifest(
    manifest: Iterable[str | tuple[str, str] | list[str]],
) -> tuple[str, ...]:
    names: list[str] = []
    for item in manifest:
        if isinstance(item, str):
            name = item
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            name = str(item[0])
        else:
            raise PurgeError("public heads/tags ref manifest is malformed")
        if not (
            name.startswith("refs/heads/")
            or name.startswith("refs/tags/")
        ):
            raise PurgeError("public ref manifest contains a non-public ref")
        names.append(name)
    normalized = tuple(sorted(set(names)))
    if len(normalized) != len(names):
        raise PurgeError("public ref manifest contains duplicate refs")
    if not normalized:
        raise PurgeError("public heads/tags ref manifest is empty")
    return normalized


def _normalize_public_ref_entries(
    manifest: Iterable[tuple[str, str] | list[str]],
) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for item in manifest:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise PurgeError("public ref manifest entries are malformed")
        name, object_id = str(item[0]), str(item[1])
        if not (
            name.startswith("refs/heads/")
            or name.startswith("refs/tags/")
        ) or not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
            raise PurgeError("public ref manifest entries are malformed")
        entries.append((name, object_id))
    normalized = tuple(sorted(set(entries)))
    if len(normalized) != len(entries) or not normalized:
        raise PurgeError("public heads/tags ref manifest is empty or duplicated")
    return normalized


def _read_refs(root: Path) -> tuple[tuple[str, str], ...]:
    raw = _git(root, "for-each-ref", "--format=%(refname)%00%(objectname)", "refs")
    refs: list[tuple[str, str]] = []
    for line in raw.splitlines():
        parts = line.split(b"\0", 1)
        if len(parts) != 2:
            continue
        name, object_id = (part.decode("utf-8", "surrogateescape") for part in parts)
        if name and object_id:
            refs.append((name, object_id))
    return tuple(sorted(set(refs)))


def _reachable_object_listing(root: Path) -> tuple[tuple[str, str], ...]:
    raw = _git(root, "rev-list", "--objects", "--all")
    entries: list[tuple[str, str]] = []
    for line in raw.splitlines():
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        object_id = parts[0].decode("ascii", "strict")
        path = (
            parts[1].decode("utf-8", "surrogateescape")
            if len(parts) == 2
            else object_id
        )
        entries.append((object_id, path))
    return tuple(sorted(entries, key=lambda item: (item[0], item[1])))


def reachable_blobs(root: Path | str) -> tuple[Blob, ...]:
    """Return every reachable blob/path occurrence from local refs."""
    repository = _repository_root(root)
    listing = _reachable_object_listing(repository)
    if not listing:
        return ()
    object_ids = tuple(dict.fromkeys(object_id for object_id, _ in listing))
    request = b"".join(object_id.encode("ascii") + b"\n" for object_id in object_ids)
    raw = _git(repository, "cat-file", "--batch", input_data=request)
    paths_by_object: dict[str, list[str]] = {}
    for object_id, path in listing:
        paths_by_object.setdefault(object_id, []).append(path)
    blobs: list[Blob] = []
    offset = 0
    while offset < len(raw):
        header_end = raw.find(b"\n", offset)
        if header_end < 0:
            raise PurgeError("invalid Git object response")
        header = raw[offset:header_end].decode("ascii", "strict").split()
        offset = header_end + 1
        if len(header) != 3:
            raise PurgeError("invalid Git object response")
        object_id, kind, size_text = header
        try:
            size = int(size_text)
        except ValueError as exc:
            raise PurgeError("invalid Git object response") from exc
        data = raw[offset : offset + size]
        if len(data) != size:
            raise PurgeError("truncated Git object response")
        offset += size
        if offset >= len(raw) or raw[offset : offset + 1] != b"\n":
            raise PurgeError("invalid Git object response")
        offset += 1
        if kind == "blob":
            paths = paths_by_object.get(object_id, [object_id])
            blobs.extend(Blob(object_id, path, data) for path in sorted(set(paths)))
    return tuple(blobs)


def _load_denylist() -> frozenset[str]:
    """Load the tracked guard's fingerprints without importing the app package."""
    path = Path(__file__).with_name("check_pii.py")
    if not path.is_file():
        raise PurgeError("the history guard denylist is unavailable")
    spec = importlib.util.spec_from_file_location("_history_purge_check_pii", path)
    if spec is None or spec.loader is None:
        raise PurgeError("the history guard denylist is unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - defensive import boundary
        raise PurgeError("the history guard denylist is unavailable") from exc
    denylist = getattr(module, "DENYLIST", None)
    if not isinstance(denylist, (set, frozenset, list, tuple)):
        raise PurgeError("the history guard denylist is unavailable")
    return frozenset(str(item) for item in denylist)


def _is_synthetic(value: str) -> bool:
    return any(pattern.fullmatch(value) for pattern in _SYNTHETIC_PATTERNS)


def _is_identity_candidate(value: Any, category: str | None, denylist: frozenset[str]) -> bool:
    if not isinstance(value, str) or not value or _is_synthetic(value):
        return False
    if value in {"Order", "Chaos"}:
        return False
    return category is not None or fingerprint(value) in denylist


def _field_path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]" if parent else f"[{key}]"
    return f"{parent}.{key}" if parent else key


def _scan_json(
    value: Any,
    *,
    object_path: str,
    field: str = "",
    parent_puuid: str | None = None,
    denylist: frozenset[str],
) -> tuple[list[IdentityOccurrence], dict[str, str]]:
    occurrences: list[IdentityOccurrence] = []
    relations: dict[str, str] = {}
    local_puuid = parent_puuid
    if isinstance(value, dict):
        candidate_puuid = value.get("puuid")
        if _is_identity_candidate(candidate_puuid, "puuid", denylist):
            local_puuid = candidate_puuid
        for key, child in value.items():
            child_field = _field_path(field, key)
            category = FIELD_CATEGORIES.get(key)
            if _is_identity_candidate(child, category, denylist):
                assert isinstance(child, str)
                occurrences.append(
                    IdentityOccurrence(
                        f"{object_path}",
                        child_field,
                        fingerprint(child),
                        child,
                        category or "generic",
                    )
                )
                if local_puuid is not None and category != "puuid":
                    previous = relations.get(child)
                    if previous is None:
                        relations[child] = local_puuid
                    elif previous != local_puuid:
                        # A reused source value cannot safely inherit one
                        # participant ordinal; it falls back to its category.
                        relations.pop(child, None)
            child_occurrences, child_relations = _scan_json(
                child,
                object_path=object_path,
                field=child_field,
                parent_puuid=local_puuid,
                denylist=denylist,
            )
            occurrences.extend(child_occurrences)
            for source, puuid in child_relations.items():
                previous = relations.get(source)
                if previous is None:
                    relations[source] = puuid
                elif previous != puuid:
                    relations.pop(source, None)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_occurrences, child_relations = _scan_json(
                child,
                object_path=object_path,
                field=_field_path(field, index),
                parent_puuid=local_puuid,
                denylist=denylist,
            )
            occurrences.extend(child_occurrences)
            for source, puuid in child_relations.items():
                previous = relations.get(source)
                if previous is None:
                    relations[source] = puuid
                elif previous != puuid:
                    relations.pop(source, None)
    return occurrences, relations


def _scan_text(blob: Blob, text: str, denylist: frozenset[str]) -> list[IdentityOccurrence]:
    candidates = _TEXT_CANDIDATE.findall(text)
    candidates.extend(match.group(2) for match in _QUOTED_CANDIDATE.finditer(text))
    occurrences: list[IdentityOccurrence] = []
    seen: set[str] = set()
    for candidate in candidates:
        if len(candidate) < 7 or candidate in seen or _is_synthetic(candidate):
            continue
        if fingerprint(candidate) not in denylist:
            continue
        seen.add(candidate)
        occurrences.append(
            IdentityOccurrence(
                f"{blob.path}@{blob.object_id[:12]}",
                "text",
                fingerprint(candidate),
                candidate,
                "generic",
            )
        )
    return occurrences


def scan_blob(blob: Blob, denylist: frozenset[str] | None = None) -> tuple[list[IdentityOccurrence], dict[str, str]]:
    """Scan one reachable blob without ever returning its value in output."""
    denylist = denylist or _load_denylist()
    try:
        text = blob.data.decode("utf-8")
    except UnicodeDecodeError:
        return [], {}
    occurrences = _scan_text(blob, text, denylist)
    relations: dict[str, str] = {}
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return occurrences, relations
    json_occurrences, json_relations = _scan_json(
        document,
        object_path=f"{blob.path}@{blob.object_id[:12]}",
        denylist=denylist,
    )
    occurrences.extend(json_occurrences)
    relations.update(json_relations)
    return occurrences, relations


def inventory_repository(root: Path | str) -> Inventory:
    """Inventory unique identity values across every reachable branch/tag blob."""
    denylist = _load_denylist()
    all_occurrences: list[IdentityOccurrence] = []
    categories: dict[str, set[str]] = {}
    relations: dict[str, str] = {}
    for blob in reachable_blobs(root):
        occurrences, blob_relations = scan_blob(blob, denylist)
        all_occurrences.extend(occurrences)
        for occurrence in occurrences:
            categories.setdefault(occurrence.value, set()).add(occurrence.category)
        for source, puuid in blob_relations.items():
            previous = relations.get(source)
            if previous is None:
                relations[source] = puuid
            elif previous != puuid:
                relations.pop(source, None)
    unique_occurrences = tuple(
        sorted(
            {
                (item.path, item.field, item.digest, item.value, item.category): item
                for item in all_occurrences
            }.values(),
            key=lambda item: (item.path, item.field, item.digest),
        )
    )
    values = tuple(sorted(categories, key=lambda item: item.encode("utf-8")))
    frozen_categories = {source: frozenset(kinds) for source, kinds in categories.items()}
    return Inventory(unique_occurrences, values, frozen_categories, relations)


def _category_priority(categories: frozenset[str]) -> str:
    for category in (
        "puuid",
        "summoner_id",
        "riot_id",
        "riot_name",
        "riot_tag",
        "name",
        "generic",
    ):
        if category in categories:
            return category
    return "generic"


def _replacement_category(source: str, categories: frozenset[str]) -> str:
    """Normalize field categories before assigning deterministic ordinals."""
    category = _category_priority(categories)
    if category in {"name", "riot_name"}:
        # Both fields identify the same participant namespace and must share
        # one ordinal space to avoid distinct names collapsing to one value.
        return "name"
    if category == "generic" and len(source) >= 40 and re.fullmatch(
        r"[A-Za-z0-9_-]+", source
    ):
        # Unstructured participant lists and text fixtures can carry PUUIDs
        # without a structured ``puuid`` key.  Keep them in the PUUID ordinal
        # space so they cannot collide with structured PUUID replacements.
        return "puuid"
    return category


def _replacement_entries(inventory: Inventory) -> tuple[tuple[str, str], ...]:
    category_values: dict[str, list[str]] = {}
    categories_by_source: dict[str, str] = {}
    for source in inventory.values:
        category = _replacement_category(source, inventory.categories[source])
        categories_by_source[source] = category
        category_values.setdefault(category, []).append(source)
    ordered_category_values = {
        category: sorted(values, key=lambda item: item.encode("utf-8"))
        for category, values in category_values.items()
    }
    puuid_ordinals = {
        source: index
        for index, source in enumerate(ordered_category_values.get("puuid", ()), 1)
    }
    category_ordinals: dict[str, dict[str, int]] = {"puuid": puuid_ordinals}
    for category, values in ordered_category_values.items():
        if category == "puuid":
            continue
        assigned = {
            source: puuid_ordinals[related]
            for source in values
            if (related := inventory.relations.get(source)) in puuid_ordinals
        }
        reserved = set(assigned.values())
        next_ordinal = 1
        for source in values:
            if source in assigned:
                continue
            while next_ordinal in reserved:
                next_ordinal += 1
            assigned[source] = next_ordinal
            reserved.add(next_ordinal)
            next_ordinal += 1
        category_ordinals[category] = assigned
    entries: list[tuple[str, str]] = []
    replacements: dict[str, str] = {}
    for source in inventory.values:
        category = categories_by_source[source]
        ordinal = category_ordinals[category][source]
        if category == "puuid":
            replacement = f"fixture-puuid-{ordinal:02d}"
        elif category == "summoner_id":
            replacement = f"fixture-summoner-{ordinal:02d}"
        elif category == "name":
            replacement = f"FixturePlayer{ordinal:02d}"
        elif category == "riot_tag":
            replacement = f"BL{ordinal:02d}"
        elif category == "riot_id":
            replacement = f"FixturePlayer{ordinal:02d}#BL{ordinal:02d}"
        else:
            replacement = f"fixture-identity-{ordinal:02d}"
        if (
            not source
            or source.startswith("#")
            or source == replacement
            or "\x00" in source
            or "\n" in source
            or "\r" in source
            or "==>" in source
        ):
            raise PurgeError("replacement map contains an unsafe identity value")
        previous = replacements.get(replacement)
        if previous is not None and previous != source:
            raise PurgeError("replacement map contains duplicate replacement values")
        replacements[replacement] = source
        entries.append((source, replacement))
    return tuple(entries)


def _map_payload(entries: Iterable[tuple[str, str]]) -> bytes:
    ordered = sorted(
        entries,
        key=lambda item: (-len(item[0].encode("utf-8")), item[0].encode("utf-8")),
    )
    return "".join(f"{source}==>{replacement}\n" for source, replacement in ordered).encode("utf-8")


def _snapshot_payload(snapshot: RepositorySnapshot) -> dict[str, Any]:
    return {
        "refs": [[name, object_id] for name, object_id in snapshot.refs],
        "object_count": snapshot.object_count,
        "object_manifest_sha256": snapshot.object_manifest_sha256,
        "commit_ids": list(snapshot.commit_ids),
        "archive_checksums": [[name, digest] for name, digest in snapshot.archive_checksums],
    }


def snapshot_digest(snapshot: RepositorySnapshot) -> str:
    return hashlib.sha256(_canonical_json(_snapshot_payload(snapshot))).hexdigest()


def _snapshot_from_payload(payload: Mapping[str, Any]) -> RepositorySnapshot:
    try:
        refs = tuple((str(item[0]), str(item[1])) for item in payload["refs"])
        archives = tuple((str(item[0]), str(item[1])) for item in payload["archive_checksums"])
        commits = tuple(str(item) for item in payload["commit_ids"])
        object_count = int(payload["object_count"])
        object_digest = str(payload["object_manifest_sha256"])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise PurgeError("backup snapshot is malformed") from exc
    return RepositorySnapshot(refs, object_count, object_digest, commits, archives)


def _archive_refs(refs: Iterable[tuple[str, str]]) -> tuple[str, ...]:
    return tuple(
        name
        for name, _ in refs
        if name.startswith("refs/heads/")
        or name.startswith("refs/tags/")
        or name.startswith("refs/remotes/origin/")
    )


def _commit_ids(root: Path) -> tuple[str, ...]:
    raw = _git(root, "rev-list", "--all")
    return tuple(sorted(set(line.decode("ascii") for line in raw.splitlines() if line)))


def snapshot_repository(root: Path | str) -> RepositorySnapshot:
    """Capture refs, reachable object manifest, commits, and archive checksums."""
    repository = _repository_root(root)
    refs = _read_refs(repository)
    listing = _reachable_object_listing(repository)
    listing_bytes = b"".join(
        f"{object_id} {path}\n".encode("utf-8", "surrogateescape")
        for object_id, path in listing
    )
    archives: list[tuple[str, str]] = []
    for ref in _archive_refs(refs):
        data = _git(repository, "archive", "--format=tar", ref)
        archives.append((ref, hashlib.sha256(data).hexdigest()))
    return RepositorySnapshot(
        refs=refs,
        object_count=len(listing),
        object_manifest_sha256=hashlib.sha256(listing_bytes).hexdigest(),
        commit_ids=_commit_ids(repository),
        archive_checksums=tuple(archives),
    )


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise PurgeError("destination parent directory does not exist")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except OSError:
            pass
        raise PurgeError("could not write external evidence") from exc


def write_replacement_map(
    path: Path | str,
    inventory: Inventory,
    snapshot: RepositorySnapshot,
    *,
    repository_root: Path | str | None = None,
) -> ReplacementMap:
    """Write a restrictive git-filter-repo map outside the repository."""
    destination = _resolve_path(path)
    if repository_root is not None:
        destination = _ensure_external_path(_repository_root(repository_root), destination, "replacement map")
    elif destination.exists() and destination.is_symlink():
        raise PurgeError("replacement map must not be a symlink")
    if destination.exists() and destination.is_dir():
        raise PurgeError("replacement map must be a file")
    entries = _replacement_entries(inventory)
    payload = _map_payload(entries)
    map_digest = hashlib.sha256(payload).hexdigest()
    header = (
        f"# version: {MAP_VERSION}\n"
        f"# inventory-count: {len(entries)}\n"
        f"# snapshot-sha256: {snapshot_digest(snapshot)}\n"
        f"# map-sha256: {map_digest}\n"
    ).encode("utf-8")
    _atomic_write(destination, header + payload)
    return ReplacementMap(tuple(entries), len(entries), snapshot_digest(snapshot), map_digest)


def load_replacement_map(
    path: Path | str,
    *,
    expected_count: int | None = None,
) -> ReplacementMap:
    """Parse and verify an external replacement map without printing values."""
    source = _resolve_path(path)
    if source.is_symlink() or not source.is_file():
        raise PurgeError("replacement map is missing or is a symlink")
    try:
        mode = stat.S_IMODE(source.stat().st_mode)
        if mode & 0o077:
            raise PurgeError("replacement map permissions must be owner-only")
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise PurgeError("replacement map cannot be read") from exc
    metadata: dict[str, str] = {}
    entries: list[tuple[str, str]] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("#"):
            if ": " in line:
                key, value = line[1:].split(": ", 1)
                metadata[key.strip()] = value.strip()
            continue
        if "==>" not in line:
            raise PurgeError("replacement map contains a malformed entry")
        old, new = line.split("==>", 1)
        if (
            not old
            or not new
            or old.startswith("#")
            or "\x00" in old
            or "\n" in old
            or "\r" in old
            or "\x00" in new
            or "\n" in new
            or "\r" in new
        ):
            raise PurgeError("replacement map contains an unsafe entry")
        if old == new or any(existing == old for existing, _ in entries):
            raise PurgeError("replacement map contains a duplicate entry")
        if any(existing == new for _, existing in entries):
            raise PurgeError("replacement map contains duplicate replacement values")
        entries.append((old, new))
    if metadata.get("version") != MAP_VERSION:
        raise PurgeError("replacement map version is unsupported")
    try:
        declared_count = int(metadata["inventory-count"])
    except (KeyError, ValueError) as exc:
        raise PurgeError("replacement map inventory count is missing") from exc
    payload = _map_payload(entries)
    actual_digest = hashlib.sha256(payload).hexdigest()
    if declared_count != len(entries) or metadata.get("map-sha256") != actual_digest:
        raise PurgeError("replacement map inventory checksum is invalid")
    snapshot_sha = metadata.get("snapshot-sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha):
        raise PurgeError("replacement map snapshot checksum is missing")
    if expected_count is not None and declared_count != expected_count:
        raise PurgeError("replacement map inventory count does not match expectation")
    return ReplacementMap(tuple(entries), declared_count, snapshot_sha, actual_digest)


def create_backup(
    root: Path | str,
    backup_dir: Path | str,
    *,
    snapshot: RepositorySnapshot | None = None,
) -> Path:
    """Create an external mirror, bundle, and checksum manifest."""
    repository = _repository_root(root)
    destination = _ensure_external_path(repository, backup_dir, "backup destination")
    if destination.exists():
        try:
            is_new_empty_directory = destination.is_dir() and not any(destination.iterdir())
        except OSError as exc:
            raise PurgeError("backup destination cannot be inspected") from exc
        if not is_new_empty_directory:
            raise PurgeError("backup destination must be a new empty directory")
        try:
            os.chmod(destination, 0o700)
        except OSError as exc:
            raise PurgeError("could not restrict backup destination") from exc
    else:
        try:
            destination.mkdir(mode=0o700)
        except OSError as exc:
            raise PurgeError("could not create backup destination") from exc
    before = snapshot or snapshot_repository(repository)
    mirror = destination / "mirror"
    bundle = destination / "refs.bundle"
    _run_command(
        ["git", "clone", "--mirror", "--no-local", str(repository), str(mirror)]
    )
    _git(repository, "bundle", "create", str(bundle), "--all")
    _git(repository, "bundle", "verify", str(bundle))
    mirror_snapshot = snapshot_repository(mirror)
    if mirror_snapshot != before:
        raise PurgeError("backup mirror does not match the pre-rewrite snapshot")
    try:
        bundle_digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    except OSError as exc:
        raise PurgeError("backup bundle cannot be read") from exc
    manifest = {
        "version": BACKUP_VERSION,
        "snapshot": _snapshot_payload(before),
        "snapshot-sha256": snapshot_digest(before),
        "bundle": {"name": "refs.bundle", "sha256": bundle_digest},
        "mirror": {"name": "mirror"},
        "owner_reviewed": False,
    }
    _atomic_write(destination / "manifest.json", _canonical_json(manifest) + b"\n")
    _lock_down_tree(destination)
    return destination / "manifest.json"


def _lock_down_tree(root: Path) -> None:
    try:
        for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir():
                os.chmod(path, 0o700)
            elif path.is_file():
                os.chmod(path, 0o600)
        os.chmod(root, 0o700)
    except OSError as exc:
        raise PurgeError("could not restrict backup permissions") from exc


def verify_backup(
    root: Path | str,
    backup_dir: Path | str,
    *,
    expected_snapshot: RepositorySnapshot | None = None,
) -> RepositorySnapshot:
    """Verify the reviewed backup's mirror, bundle, and current ref snapshot."""
    repository = _repository_root(root)
    destination = _ensure_external_path(repository, backup_dir, "backup destination")
    manifest_path = destination / "manifest.json"
    bundle = destination / "refs.bundle"
    mirror = destination / "mirror"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot = _snapshot_from_payload(manifest["snapshot"])
        declared_snapshot_digest = str(manifest["snapshot-sha256"])
        bundle_digest = str(manifest["bundle"]["sha256"])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PurgeError("backup manifest is missing or malformed") from exc
    if manifest.get("version") != BACKUP_VERSION:
        raise PurgeError("backup manifest version is unsupported")
    if declared_snapshot_digest != snapshot_digest(snapshot):
        raise PurgeError("backup snapshot checksum is invalid")
    if expected_snapshot is not None and snapshot != expected_snapshot:
        raise PurgeError("backup does not match the expected pre-rewrite snapshot")
    try:
        actual_bundle_digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    except OSError as exc:
        raise PurgeError("backup bundle is missing") from exc
    if actual_bundle_digest != bundle_digest:
        raise PurgeError("backup bundle checksum is invalid")
    if not mirror.is_dir():
        raise PurgeError("backup mirror is missing")
    _git(repository, "bundle", "verify", str(bundle))
    if snapshot_repository(mirror) != snapshot:
        raise PurgeError("backup mirror checksum does not match its manifest")
    if snapshot_repository(repository) != snapshot:
        raise PurgeError("repository refs changed since the backup was created")
    return snapshot


def _normalize_comment_id(value: str | int | None) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value > 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
        return value
    return None


def _comment_id_from_url(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    expected_path = f"/{AUTHORIZED_REPOSITORY}/issues/{AUTHORIZATION_ISSUE}"
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.path != expected_path
        or not parsed.fragment.startswith("issuecomment-")
    ):
        return None
    return _normalize_comment_id(parsed.fragment.removeprefix("issuecomment-"))


def _authorization_locator_from_file(path: Path) -> tuple[str, str] | None:
    """Read a locator record, never trusting local author claims as proof."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != AUTHORIZATION_RECORD_VERSION:
        return None
    comment_id = _normalize_comment_id(payload.get("comment_id"))
    comment_url = payload.get("comment_url")
    url_id = _comment_id_from_url(comment_url)
    if comment_id is not None and comment_url is not None:
        return None
    if comment_id is not None:
        return "id", comment_id
    if url_id is not None:
        return "url", url_id
    return None


def _authorization_locator(
    *,
    authorization_file: Path | None = None,
    authorization_comment_id: str | int | None = None,
    authorization_comment_url: str | None = None,
) -> tuple[str, str] | None:
    provided = sum(
        value is not None
        for value in (
            authorization_file,
            authorization_comment_id,
            authorization_comment_url,
        )
    )
    if provided > 1:
        raise PurgeError("provide only one authorization comment locator")
    if authorization_file is not None:
        return _authorization_locator_from_file(authorization_file)
    comment_id = _normalize_comment_id(authorization_comment_id)
    if comment_id is not None:
        return "id", comment_id
    url_id = _comment_id_from_url(authorization_comment_url)
    if url_id is not None:
        return "url", url_id
    return None


def _fetch_authorization_comment(comment_id: str) -> Mapping[str, Any] | None:
    """Fetch one public issue comment through a bounded, read-only API call."""
    endpoint = (
        f"https://api.github.com/repos/{AUTHORIZED_REPOSITORY}/issues/comments/{comment_id}"
    )
    request = Request(
        endpoint,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "bhayanak-legends-history-purge",
        },
        method="GET",
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=AUTHORIZATION_API_TIMEOUT) as response:
            if getattr(response, "status", 200) != 200:
                return None
            raw = response.read(1_048_577)
    except (HTTPError, URLError, OSError, TimeoutError):
        return None
    if len(raw) > 1_048_576:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _authorization_comment_matches(
    payload: Mapping[str, Any] | None,
    comment_id: str,
) -> bool:
    if payload is None or comment_id != AUTHORIZED_COMMENT_ID:
        return False
    payload_id = _normalize_comment_id(payload.get("id"))
    if payload_id != comment_id:
        return False
    issue_url = (
        f"https://api.github.com/repos/{AUTHORIZED_REPOSITORY}/issues/{AUTHORIZATION_ISSUE}"
    )
    html_url = (
        f"https://github.com/{AUTHORIZED_REPOSITORY}/issues/{AUTHORIZATION_ISSUE}"
        f"#issuecomment-{comment_id}"
    )
    if payload.get("issue_url") != issue_url or payload.get("html_url") != html_url:
        return False
    user = payload.get("user")
    author = user.get("login") if isinstance(user, dict) else None
    if author != AUTHORIZED_OWNER or payload.get("author_association") != "OWNER":
        return False
    body = payload.get("body")
    return isinstance(body, str) and body == AUTHORIZATION


def _authorization_text(value: str | None, path: Path | None) -> str:
    # Kept as a compatibility seam for callers that need to inspect supplied
    # text.  Neither a direct string nor a copied issue body grants access.
    if value is not None and path is not None:
        raise PurgeError("provide only one authorization input")
    if value is not None:
        return value
    if path is None:
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PurgeError("authorization record cannot be read") from exc
    body = payload.get("body") if isinstance(payload, dict) else ""
    return body if isinstance(body, str) else ""


def authorization_matches(
    value: str | None = None,
    path: Path | None = None,
    *,
    comment_id: str | int | None = None,
    comment_url: str | None = None,
    fetcher: Any = None,
) -> bool:
    """Validate the canonical owner's exact issue-comment authorization."""
    if value is not None:
        # ``--authorization`` is intentionally not an authorization channel:
        # a caller-supplied string has no owner provenance.
        if path is not None or comment_id is not None or comment_url is not None:
            raise PurgeError("provide only one authorization input")
        return False
    locator = _authorization_locator(
        authorization_file=path,
        authorization_comment_id=comment_id,
        authorization_comment_url=comment_url,
    )
    if locator is None:
        return False
    _, resolved_id = locator
    if resolved_id != AUTHORIZED_COMMENT_ID:
        return False
    lookup = fetcher or _fetch_authorization_comment
    try:
        payload = lookup(resolved_id)
    except Exception:
        # API/network seams fail closed without echoing remote response data.
        return False
    return _authorization_comment_matches(payload, resolved_id)

def preflight_apply(
    root: Path | str,
    map_path: Path | str,
    backup_dir: Path | str,
    *,
    authorization: str | None = None,
    authorization_file: Path | None = None,
    authorization_comment_id: str | int | None = None,
    authorization_comment_url: str | None = None,
    expected_count: int | None = None,
    backup_reviewed: bool = False,
) -> ApplyPlan:
    """Validate all local prerequisites before the ref-mutating command.

    The GitHub lookup is intentionally last: malformed local paths, maps,
    counts, and backups fail without any network access.
    """
    repository = _repository_root(root)
    external_map = _ensure_external_path(repository, map_path, "replacement map")
    external_auth_file = (
        _ensure_external_path(repository, authorization_file, "authorization record")
        if authorization_file is not None
        else None
    )
    if expected_count is None or expected_count < 1:
        raise PurgeError("a positive expected inventory count is required")
    if not backup_reviewed:
        raise PurgeError("an owner-reviewed backup attestation is required")
    replacement_map = load_replacement_map(external_map, expected_count=expected_count)
    current = snapshot_repository(repository)
    backup_snapshot = verify_backup(repository, backup_dir, expected_snapshot=current)
    if replacement_map.snapshot_sha256 != snapshot_digest(backup_snapshot):
        raise PurgeError("replacement map was not generated from the reviewed backup")
    inventory = inventory_repository(repository)
    if inventory.count != expected_count:
        raise PurgeError("scanned inventory count does not match expectation")
    expected_entries = dict(_replacement_entries(inventory))
    if dict(replacement_map.entries) != expected_entries:
        raise PurgeError("replacement map does not cover the reviewed inventory")
    public_refs = public_ref_manifest(repository)
    locator = _authorization_locator(
        authorization_file=external_auth_file,
        authorization_comment_id=authorization_comment_id,
        authorization_comment_url=authorization_comment_url,
    )
    if locator is None or not authorization_matches(
        authorization,
        external_auth_file,
        comment_id=authorization_comment_id,
        comment_url=authorization_comment_url,
    ):
        raise PurgeError(
            "validated owner issue-comment authorization is required; "
            "no refs or Git remotes were changed"
        )
    return ApplyPlan(
        repository,
        external_map,
        _ensure_external_path(repository, backup_dir, "backup destination"),
        current,
        replacement_map,
        backup_reviewed,
        public_refs,
    )


def _run_filter_repo(plan: ApplyPlan) -> None:
    # This is intentionally a local command.  No `git push`, `ls-remote`, or
    # other remote operation exists in this module.
    _run_command(
        [
            "git",
            "-C",
            str(plan.root),
            "filter-repo",
            "--sensitive-data-removal",
            "--replace-text",
            str(plan.map_path),
            "--force",
        ]
    )


def _selected_origin_refs(root: Path) -> tuple[str, ...]:
    """Return refs used for reachability checks, requiring public refs."""
    repository = _repository_root(root)
    _public_ref_entries(repository)
    refs = tuple(
        name
        for name, _ in _read_refs(repository)
        if name.startswith("refs/heads/")
        or name.startswith("refs/tags/")
        or name.startswith("refs/remotes/origin/")
    )
    if not refs:
        raise PurgeError("selected origin refs are empty")
    return refs


def reachable_origin_commits(root: Path | str) -> frozenset[str]:
    """Return commits reachable from origin branch/tag refs only."""
    repository = _repository_root(root)
    refs = _selected_origin_refs(repository)
    raw = _git(repository, "rev-list", *refs)
    return frozenset(line.decode("ascii") for line in raw.splitlines() if line)


_DROP = object()


def _project(value: Any, key: str | None = None) -> Any:
    if key in IDENTITY_FIELDS:
        return _DROP
    if key == "participants" and isinstance(value, list) and all(
        isinstance(item, str) for item in value
    ):
        return _DROP
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for child_key, child in value.items():
            projected = _project(child, child_key)
            if projected is not _DROP:
                result[child_key] = projected
        return result
    if isinstance(value, list):
        result_list: list[Any] = []
        for child in value:
            projected = _project(child)
            result_list.append(None if projected is _DROP else projected)
        return result_list
    return value


def non_identity_projection(value: Any) -> Any:
    """Return a fixture projection with identity-bearing values removed."""
    projected = _project(value)
    return {} if projected is _DROP else projected


def fixture_projections(root: Path | str) -> dict[str, frozenset[str]]:
    """Hash non-identity fixture projections across all reachable fixture blobs."""
    projections: dict[str, set[str]] = {}
    for blob in reachable_blobs(root):
        if "tests/fixtures/" not in blob.path.replace("\\", "/"):
            continue
        try:
            document = json.loads(blob.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            digest = hashlib.sha256(blob.data).hexdigest()
        else:
            digest = hashlib.sha256(_canonical_json(non_identity_projection(document))).hexdigest()
        projections.setdefault(blob.path, set()).add(digest)
    return {path: frozenset(values) for path, values in sorted(projections.items())}


def compare_fixture_projections(before_root: Path | str, after_root: Path | str) -> bool:
    """Compare all non-identity fixture projections without exposing values."""
    return fixture_projections(before_root) == fixture_projections(after_root)


def run_history_guard(
    root: Path | str,
    *,
    check_pii_path: Path | str | None = None,
) -> bool:
    """Run check_pii.py --history while keeping its captured report private."""
    repository = _repository_root(root)
    if check_pii_path is None:
        candidates = (
            repository / "tools" / "check_pii.py",
            repository / "backend" / "tools" / "check_pii.py",
            Path(__file__).with_name("check_pii.py"),
        )
        checker = next((candidate for candidate in candidates if candidate.is_file()), None)
    else:
        checker = _resolve_path(check_pii_path)
    if checker is None or not checker.is_file():
        raise PurgeError("history guard script is unavailable")
    command = [sys.executable, str(checker), "--history"]
    try:
        checker_root = checker.resolve().parents[2]
    except IndexError:
        checker_root = None
    if checker_root != repository:
        command.extend(["--root", str(repository)])
    try:
        result = subprocess.run(
            command,
            cwd=str(repository),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise PurgeError("history guard could not be started") from exc
    return result.returncode == 0


def _assert_full_mirror(root: Path) -> None:
    try:
        bare = _git(root, "rev-parse", "--is-bare-repository").strip()
        mirror = _git(root, "config", "--get", "remote.origin.mirror").strip()
        refspec = _git(root, "config", "--get-all", "remote.origin.fetch")
    except PurgeError as exc:
        raise PurgeError("verification repository is not a full mirror") from exc
    if bare != b"true" or mirror != b"true" or b"+refs/*:refs/*" not in refspec.splitlines():
        raise PurgeError("verification repository is not a full mirror")


def _normalize_origin_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    return normalized[:-4] if normalized.endswith(".git") else normalized


def _assert_canonical_origin(root: Path, expected: str | None = None) -> str:
    try:
        actual = _git(root, "config", "--get", "remote.origin.url").decode("utf-8").strip()
    except (PurgeError, UnicodeDecodeError) as exc:
        raise PurgeError("verification repository has no origin URL") from exc
    allowed = {_normalize_origin_url(value) for value in CANONICAL_ORIGIN_URLS}
    if _normalize_origin_url(actual) not in allowed:
        raise PurgeError("verification repository origin URL is not canonical")
    if expected is not None and _normalize_origin_url(expected) != _normalize_origin_url(actual):
        raise PurgeError("verification repository origin URL does not match evidence")
    return actual


def create_origin_verification_mirror(
    root: Path | str,
    verification_root: Path | str,
) -> tuple[Path, str]:
    """Clone canonical origin into a new external full mirror."""
    repository = _repository_root(root)
    destination = _ensure_new_external_path(
        repository,
        verification_root,
        "verification repository",
    )
    _run_command(
        [
            "git",
            "clone",
            "--mirror",
            CANONICAL_ORIGIN_URL,
            str(destination),
        ]
    )
    _assert_full_mirror(destination)
    origin_url = _assert_canonical_origin(destination)
    public_ref_manifest(destination)
    return destination, origin_url


def create_verification_mirror(
    source_root: Path | str,
    verification_root: Path | str,
) -> Path:
    """Create a new external mirror from the rewritten local candidate."""
    source = _repository_root(source_root)
    destination = _ensure_new_external_path(
        source,
        verification_root,
        "verification repository",
    )
    _run_command(
        [
            "git",
            "clone",
            "--mirror",
            "--no-local",
            str(source),
            str(destination),
        ]
    )
    _assert_full_mirror(destination)
    public_ref_manifest(destination)
    return destination


def verify_post_rewrite(
    rewritten_root: Path | str,
    backup_root: Path | str,
    original_commit_ids: Iterable[str],
    *,
    check_pii_path: Path | str | None = None,
    expected_public_refs: Iterable[str | tuple[str, str] | list[str]] | None = None,
    expected_post_public_refs: Iterable[tuple[str, str] | list[str]] | None = None,
) -> VerificationResult:
    """Verify a fresh rewrite against all four non-vacuous gates."""
    rewritten = _repository_root(rewritten_root)
    public_ref_manifest(rewritten)
    _assert_full_mirror(rewritten)
    expected_names = (
        _normalize_public_ref_manifest(expected_public_refs)
        if expected_public_refs is not None
        else public_ref_names(backup_root)
    )
    actual_manifest = public_ref_manifest(rewritten)
    actual_names = tuple(name for name, _ in actual_manifest)
    names_equal = actual_names == expected_names
    exact_post_equal = (
        expected_post_public_refs is None
        or actual_manifest == _normalize_public_ref_entries(expected_post_public_refs)
    )
    manifest_equal = names_equal and exact_post_equal
    guard_passed = run_history_guard(rewritten, check_pii_path=check_pii_path)
    reachable = reachable_origin_commits(rewritten)
    original = frozenset(str(item) for item in original_commit_ids)
    still_reachable = tuple(sorted(reachable & original))
    projection_equal = compare_fixture_projections(backup_root, rewritten)
    result = VerificationResult(
        guard_passed,
        still_reachable,
        projection_equal,
        manifest_equal,
    )
    if not names_equal:
        raise PurgeError("public heads/tags ref manifest changed")
    if not exact_post_equal:
        raise PurgeError("rewritten public ref OID manifest changed")
    if not guard_passed:
        raise PurgeError("fresh-clone history guard found findings")
    if still_reachable:
        raise PurgeError("original commits remain reachable from origin refs")
    if not projection_equal:
        raise PurgeError("non-identity fixture projection changed")
    return result


def post_rewrite_checklist() -> list[dict[str, str]]:
    """Return the explicit owner-only actions that this utility never performs."""
    return [
        {"id": identifier, "status": "owner-required", "requirement": requirement}
        for identifier, requirement in POST_REWRITE_CHECKLIST
    ]


def write_evidence_record(path: Path | str, record: Mapping[str, Any], *, root: Path | str) -> Path:
    """Write a JSON evidence record outside the rewritten repository."""
    repository = _repository_root(root)
    destination = _ensure_external_path(repository, path, "evidence record")
    safe_record = json.loads(json.dumps(record, sort_keys=True))
    _atomic_write(destination, _canonical_json(safe_record) + b"\n")
    return destination
def _load_evidence_record(path: Path | str, *, root: Path) -> tuple[Path, dict[str, Any]]:
    """Load an owner-only external evidence record without trusting its claims."""
    repository = _repository_root(root)
    destination = _ensure_external_path(repository, path, "evidence record")
    if destination.is_symlink() or not destination.is_file():
        raise PurgeError("evidence record is missing or is a symlink")
    try:
        mode = stat.S_IMODE(destination.stat().st_mode)
        if mode & 0o077:
            raise PurgeError("evidence record permissions must be owner-only")
        payload = json.loads(destination.read_text(encoding="utf-8"))
    except PurgeError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PurgeError("evidence record cannot be read") from exc
    if not isinstance(payload, dict) or payload.get("version") != EVIDENCE_VERSION:
        raise PurgeError("evidence record version is unsupported")
    return destination, payload


def _validate_finalization_evidence(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate post-push gates and every owner-completed checklist item."""
    if evidence.get("mode") not in {"apply-local-only", "finalize-map-deletion"}:
        raise PurgeError("evidence record is not an apply record")
    if evidence.get("external_map_deleted") is not False:
        raise PurgeError("evidence record does not require map finalization")
    if evidence.get("force_push_performed") is not True:
        raise PurgeError("origin force-update evidence is incomplete")
    try:
        pre_manifest = _normalize_public_ref_entries(
            evidence["pre_rewrite_public_ref_manifest"]
        )
        post_manifest = _normalize_public_ref_entries(
            evidence["post_rewrite_public_ref_manifest"]
        )
    except (KeyError, TypeError) as exc:
        raise PurgeError("evidence record lacks exact public ref manifests") from exc
    if tuple(name for name, _ in pre_manifest) != tuple(name for name, _ in post_manifest):
        raise PurgeError("evidence record public ref names changed")

    def validate_verification(
        payload: Any,
        *,
        label: str,
        provenance: str,
        expected_manifest: tuple[tuple[str, str], ...],
        computed_by: str,
    ) -> None:
        if not isinstance(payload, dict):
            raise PurgeError(f"evidence record lacks {label} verification")
        if payload.get("computed") is not True or payload.get("computed_by") != computed_by:
            raise PurgeError(f"evidence record {label} was not computed by the tool")
        if payload.get("provenance") != provenance:
            raise PurgeError(f"evidence record {label} provenance is invalid")
        if (
            payload.get("fresh_clone") is not True
            or payload.get("verification_repo_kind") != "full-mirror"
        ):
            raise PurgeError(f"evidence record {label} is not a fresh full mirror")
        if (
            not isinstance(payload.get("verification_repo"), str)
            or not payload["verification_repo"].strip()
        ):
            raise PurgeError(f"evidence record lacks {label} mirror provenance")
        if payload.get("history_guard_passed") is not True:
            raise PurgeError(f"evidence record lacks a successful {label} history guard")
        if payload.get("fixture_projection_equal") is not True:
            raise PurgeError(f"evidence record lacks {label} projection equality")
        if payload.get("public_refs_manifest_equal") is not True:
            raise PurgeError(f"evidence record lacks exact {label} ref verification")
        if payload.get("original_commits_reachable") != []:
            raise PurgeError(f"evidence record retains original commits in {label}")
        try:
            actual_manifest = _normalize_public_ref_entries(payload["public_ref_manifest"])
        except (KeyError, TypeError) as exc:
            raise PurgeError(f"evidence record lacks {label} ref manifest") from exc
        if actual_manifest != expected_manifest:
            raise PurgeError(f"evidence record {label} ref manifest does not match apply evidence")
    validate_verification(
        evidence.get("verification"),
        label="candidate",
        provenance="candidate-local-external-mirror",
        expected_manifest=post_manifest,
        computed_by="history_purge.apply",
    )
    validate_verification(
        evidence.get("post_push_verification"),
        label="canonical-origin",
        provenance="canonical-origin-fresh-mirror",
        expected_manifest=post_manifest,
        computed_by="history_purge.verify_origin",
    )
    candidate_verification = evidence["verification"]
    post_push_verification = evidence["post_push_verification"]
    if (
        candidate_verification["verification_repo"]
        == post_push_verification["verification_repo"]
    ):
        raise PurgeError("candidate and canonical-origin mirrors must be distinct")
    checker_path = evidence.get("check_pii_path")
    checker_digest = evidence.get("check_pii_sha256")
    canonical_checker = Path(__file__).with_name("check_pii.py").resolve()
    try:
        current_checker_digest = hashlib.sha256(canonical_checker.read_bytes()).hexdigest()
    except OSError as exc:
        raise PurgeError("history guard script is unavailable") from exc
    if (
        checker_path != str(canonical_checker)
        or checker_digest != current_checker_digest
    ):
        raise PurgeError("evidence record check_pii.py identity is stale")

    checklist = evidence.get("checklist")
    if not isinstance(checklist, list):
        raise PurgeError("evidence record checklist is missing")
    expected_ids = {identifier for identifier, _ in POST_REWRITE_CHECKLIST}
    by_id: dict[str, dict[str, Any]] = {}
    for item in checklist:
        if not isinstance(item, dict):
            raise PurgeError("evidence record checklist is malformed")
        identifier = item.get("id")
        status = item.get("status")
        if (
            not isinstance(identifier, str)
            or identifier not in expected_ids
            or identifier in by_id
            or not isinstance(status, str)
        ):
            raise PurgeError("evidence record checklist is malformed")
        by_id[identifier] = item
    if set(by_id) != expected_ids:
        raise PurgeError("evidence record checklist is incomplete")
    optional_ids = {
        "notify_collaborators_to_reclone",
        "notify_known_fork_owners",
    }
    for identifier, item in by_id.items():
        status = item["status"]
        if identifier == _MAP_DELETION_CHECKLIST_ID:
            if status != "owner-required":
                raise PurgeError("map deletion checklist must be owner-required before finalization")
            continue
        if status == "completed":
            note = item.get("evidence")
            if not isinstance(note, str) or not note.strip():
                raise PurgeError(f"checklist item {identifier} lacks evidence")
            continue
        if status == "not-applicable" and identifier in optional_ids:
            reason = item.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise PurgeError(f"checklist item {identifier} lacks an N/A reason")
            continue
        raise PurgeError(f"checklist item {identifier} cannot be {status}")
    return [dict(item) for item in checklist]


def _verify_computed_post_push(
    evidence: Mapping[str, Any],
    repository: Path,
    pre_manifest: tuple[tuple[str, str], ...],
    post_manifest: tuple[tuple[str, str], ...],
) -> VerificationResult:
    payload = evidence.get("post_push_verification")
    if not isinstance(payload, dict):
        raise PurgeError("computed canonical-origin verification is missing")
    verification_root = _ensure_external_path(
        repository,
        payload.get("verification_repo"),
        "canonical-origin verification repository",
    )
    _assert_full_mirror(verification_root)
    origin_url = payload.get("origin_url")
    if not isinstance(origin_url, str):
        raise PurgeError("computed canonical-origin URL is missing")
    actual_origin_url = _assert_canonical_origin(verification_root, origin_url)
    try:
        pre_snapshot = _snapshot_from_payload(evidence["pre_rewrite_snapshot"])
        backup_dir = _ensure_external_path(repository, evidence["backup_dir"], "backup destination")
        backup_mirror = _repository_root(backup_dir / "mirror")
    except (KeyError, TypeError, ValueError) as exc:
        raise PurgeError("evidence record lacks post-push verification inputs") from exc
    _assert_full_mirror(backup_mirror)
    checker = Path(__file__).with_name("check_pii.py").resolve()
    result = verify_post_rewrite(
        verification_root,
        backup_mirror,
        pre_snapshot.commit_ids,
        check_pii_path=checker,
        expected_public_refs=pre_manifest,
        expected_post_public_refs=post_manifest,
    )
    actual_manifest = public_ref_manifest(verification_root)
    expected_values = {
        "history_guard_passed": result.history_guard_passed,
        "original_commits_reachable": list(result.original_commits_reachable),
        "fixture_projection_equal": result.fixture_projection_equal,
        "public_refs_manifest_equal": result.public_refs_manifest_equal,
        "public_ref_manifest": [list(item) for item in actual_manifest],
    }
    if any(payload.get(key) != value for key, value in expected_values.items()):
        raise PurgeError("computed canonical-origin verification does not match the mirror")
    if _normalize_origin_url(payload["origin_url"]) != _normalize_origin_url(actual_origin_url):
        raise PurgeError("computed canonical-origin URL changed")
    return result


def finalize_map_deletion(
    root: Path | str,
    map_path: Path | str,
    evidence_path: Path | str,
) -> Path:
    """Securely delete the map after owner-completed external evidence."""
    repository = _repository_root(root)
    evidence_destination, evidence = _load_evidence_record(
        evidence_path,
        root=repository,
    )
    checklist = _validate_finalization_evidence(evidence)
    try:
        pre_manifest = _normalize_public_ref_entries(
            evidence["pre_rewrite_public_ref_manifest"]
        )
        post_manifest = _normalize_public_ref_entries(
            evidence["post_rewrite_public_ref_manifest"]
        )
    except (KeyError, TypeError) as exc:
        raise PurgeError("evidence record lacks exact public ref manifests") from exc
    _verify_computed_post_push(
        evidence,
        repository,
        pre_manifest,
        post_manifest,
    )
    map_destination = _ensure_external_path(repository, map_path, "replacement map")
    recorded_map_path = evidence.get("replacement_map_path")
    if recorded_map_path is not None and _resolve_path(recorded_map_path) != map_destination:
        raise PurgeError("replacement map does not match the evidence record")
    expected_digest = evidence.get("replacement_map_sha256")
    expected_count = evidence.get("replacement_inventory_count")
    if (
        not isinstance(expected_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
        or isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or expected_count < 1
    ):
        raise PurgeError("evidence record replacement map metadata is malformed")
    replacement_map = load_replacement_map(
        map_destination,
        expected_count=expected_count,
    )
    if replacement_map.map_sha256 != expected_digest:
        raise PurgeError("replacement map checksum does not match the evidence record")
    pending = dict(evidence)
    pending["map_deletion_pending"] = True
    write_evidence_record(evidence_destination, pending, root=repository)
    secure_delete(map_destination)
    updated = dict(pending)
    updated["map_deletion_pending"] = False
    updated["external_map_deleted"] = True
    updated["map_deletion_finalized"] = True
    updated["checklist"] = [
        (
            {
                **item,
                "status": "completed",
                "evidence": "secure deletion completed by finalize-map-deletion",
            }
            if item.get("id") == _MAP_DELETION_CHECKLIST_ID
            else item
        )
        for item in checklist
    ]
    write_evidence_record(evidence_destination, updated, root=repository)
    return evidence_destination



def secure_delete(path: Path | str) -> None:
    """Best-effort overwrite, fsync, and unlink of an external sensitive file."""
    target = _resolve_path(path)
    if target.is_symlink() or not target.is_file():
        raise PurgeError("external map is missing or is a symlink")
    try:
        size = target.stat().st_size
        with target.open("r+b") as stream:
            remaining = size
            while remaining:
                chunk = min(1024 * 1024, remaining)
                stream.write(secrets.token_bytes(chunk))
                remaining -= chunk
            stream.flush()
            os.fsync(stream.fileno())
        target.unlink()
        try:
            descriptor = os.open(str(target.parent), os.O_DIRECTORY)
        except OSError:
            descriptor = -1
        if descriptor >= 0:
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except OSError as exc:
        raise PurgeError("could not securely delete external map") from exc


def _positive_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="inventory and write an external map only")
    modes.add_argument("--apply", action="store_true", help="rewrite only this local repository after preflight")
    modes.add_argument(
        "--verify-origin",
        action="store_true",
        help="clone canonical origin and record post-push verification evidence",
    )
    modes.add_argument(
        "--finalize-map-deletion",
        action="store_true",
        help="securely delete the external map after owner evidence is complete",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository or mirror to inspect")
    parser.add_argument("--map-path", type=Path, help="external replacement map destination")
    parser.add_argument("--backup-dir", type=Path, help="external backup mirror/bundle directory")
    parser.add_argument(
        "--expected-inventory-count",
        type=_positive_count,
        help="expected number of unique replacement-map source values",
    )
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument(
        "--authorization",
        help="rejected legacy sentence input; use a verified comment ID or URL",
    )
    auth.add_argument(
        "--authorization-file",
        type=Path,
        help="external JSON locator record (version + comment_id or comment_url)",
    )
    auth.add_argument(
        "--authorization-comment-id",
        help="explicit GitHub issue-comment ID to verify read-only",
    )
    auth.add_argument(
        "--authorization-comment-url",
        help="canonical GitHub issue-comment URL to verify read-only",
    )
    parser.add_argument(
        "--backup-reviewed",
        action="store_true",
        help="attest that the external backup was reviewed by the repository owner",
    )
    parser.add_argument("--evidence-path", type=Path, help="external JSON evidence record destination")
    parser.add_argument("--verification-repo", type=Path, help="fresh clone/mirror for post-rewrite verification")
    parser.add_argument("--check-pii", type=Path, help="check_pii.py to run for post-rewrite verification")
    return parser


def _print_inventory(inventory: Inventory) -> None:
    for occurrence in inventory.occurrences:
        path = occurrence.path.replace(occurrence.value, "<redacted>")
        field = occurrence.field.replace(occurrence.value, "<redacted>")
        print(f"{path}: {field}: sha256:{occurrence.digest}")


def _dry_run(args: argparse.Namespace, repository: Path) -> int:
    if args.map_path is None:
        raise PurgeError("dry-run mode requires --map-path")
    external_map = _ensure_external_path(repository, args.map_path, "replacement map")
    before = snapshot_repository(repository)
    inventory = inventory_repository(repository)
    if args.expected_inventory_count is not None and inventory.count != args.expected_inventory_count:
        raise PurgeError("scanned inventory count does not match expectation")
    replacement_map = write_replacement_map(
        external_map,
        inventory,
        before,
        repository_root=repository,
    )
    if args.backup_dir is not None:
        create_backup(repository, args.backup_dir, snapshot=before)
    after = snapshot_repository(repository)
    if after != before:
        raise PurgeError("dry run changed repository refs or objects")
    _print_inventory(inventory)
    print(
        json.dumps(
            {
                "mode": "dry-run",
                "reachable_blobs": len(reachable_blobs(repository)),
                "inventory_count": replacement_map.inventory_count,
                "map_sha256": replacement_map.map_sha256,
                "map_path": str(external_map),
                "refs_unchanged": True,
                "remote_contacted": False,
                "force_push": False,
                "backup_created": args.backup_dir is not None,
            },
            sort_keys=True,
        )
    )
    return 0


def _apply(args: argparse.Namespace, repository: Path) -> int:
    if args.map_path is None:
        raise PurgeError("apply mode requires --map-path")
    if args.backup_dir is None:
        raise PurgeError("apply mode requires an external backup directory")
    if args.verification_repo is None:
        raise PurgeError("apply mode requires a fresh verification repository path")
    if args.check_pii is None:
        raise PurgeError("apply mode requires --check-pii")
    if args.evidence_path is None:
        raise PurgeError("apply mode requires --evidence-path")
    external_map = _ensure_external_path(repository, args.map_path, "replacement map")
    evidence_path = _ensure_new_external_path(
        repository,
        args.evidence_path,
        "evidence record",
    )
    if evidence_path == external_map:
        raise PurgeError("evidence record must use a path separate from the replacement map")
    verification_path = _ensure_new_external_path(
        repository,
        args.verification_repo,
        "verification repository",
    )
    checker = _resolve_path(args.check_pii).resolve()
    canonical_checker = Path(__file__).with_name("check_pii.py").resolve()
    if checker != canonical_checker or not checker.is_file():
        raise PurgeError("apply requires the canonical backend/tools/check_pii.py")
    try:
        checker_digest = hashlib.sha256(checker.read_bytes()).hexdigest()
    except OSError as exc:
        raise PurgeError("history guard script is unavailable") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", checker_digest):
        raise PurgeError("history guard script checksum is invalid")
    _assert_full_mirror(repository)
    plan = preflight_apply(
        repository,
        external_map,
        args.backup_dir,
        authorization=args.authorization,
        authorization_file=args.authorization_file,
        authorization_comment_id=args.authorization_comment_id,
        authorization_comment_url=args.authorization_comment_url,
        expected_count=args.expected_inventory_count,
        backup_reviewed=args.backup_reviewed,
    )
    _run_filter_repo(plan)
    post_snapshot = snapshot_repository(repository)
    post_candidate_public_refs = public_ref_manifest(repository)
    verification_root = create_verification_mirror(repository, verification_path)
    verification = verify_post_rewrite(
        verification_root,
        plan.backup_dir / "mirror",
        plan.snapshot.commit_ids,
        check_pii_path=checker,
        expected_public_refs=plan.public_ref_manifest,
        expected_post_public_refs=post_candidate_public_refs,
    )
    post_public_refs = public_ref_manifest(verification_root)
    evidence: dict[str, Any] = {
        "version": EVIDENCE_VERSION,
        "mode": "apply-local-only",
        "pre_rewrite_snapshot": _snapshot_payload(plan.snapshot),
        "post_rewrite_snapshot": _snapshot_payload(post_snapshot),
        "pre_rewrite_public_ref_manifest": [list(item) for item in plan.public_ref_manifest],
        "post_rewrite_public_ref_manifest": [list(item) for item in post_public_refs],
        "replacement_map_path": str(plan.map_path),
        "replacement_inventory_count": plan.replacement_map.inventory_count,
        "backup_dir": str(plan.backup_dir),
        "replacement_map_sha256": plan.replacement_map.map_sha256,
        "backup_reviewed": plan.backup_reviewed,
        "check_pii_path": str(checker),
        "check_pii_sha256": checker_digest,
        "verification_repo": str(verification_root),
        "verification_repo_kind": "full-mirror",
        "remote_contacted": False,
        "force_push_performed": False,
        "verification": {
            "computed": True,
            "computed_by": "history_purge.apply",
            "provenance": "candidate-local-external-mirror",
            "fresh_clone": True,
            "verification_repo_kind": "full-mirror",
            "verification_repo": str(verification_root),
            "history_guard_passed": verification.history_guard_passed,
            "original_commits_reachable": list(verification.original_commits_reachable),
            "fixture_projection_equal": verification.fixture_projection_equal,
            "public_refs_manifest_equal": verification.public_refs_manifest_equal,
            "public_ref_manifest": [list(item) for item in post_public_refs],
        },
        "post_push_verification": None,
        "checklist": post_rewrite_checklist(),
        "external_map_deleted": False,
    }
    write_evidence_record(evidence_path, evidence, root=repository)
    print(
        json.dumps(
            {
                "mode": "apply-local-only",
                "replacement_inventory_count": plan.replacement_map.inventory_count,
                "pre_rewrite_snapshot_sha256": snapshot_digest(plan.snapshot),
                "post_rewrite_snapshot_sha256": snapshot_digest(post_snapshot),
                "pre_rewrite_public_ref_manifest": list(plan.public_ref_manifest),
                "post_rewrite_public_ref_manifest": list(post_public_refs),
                "public_refs_manifest_equal": verification.public_refs_manifest_equal,
                "remote_contacted": False,
                "force_push": False,
                "owner_review_required_before_remote_update": True,
                "evidence_path": str(evidence_path),
                "external_map_deleted": False,
            },
            sort_keys=True,
        )
    )
    return 0
def _verify_origin(args: argparse.Namespace, repository: Path) -> int:
    if args.verification_repo is None:
        raise PurgeError("verify-origin mode requires --verification-repo")
    if args.evidence_path is None:
        raise PurgeError("verify-origin mode requires --evidence-path")
    evidence_path, evidence = _load_evidence_record(
        args.evidence_path,
        root=repository,
    )
    if evidence.get("mode") != "apply-local-only" or evidence.get("external_map_deleted") is not False:
        raise PurgeError("verify-origin requires an active apply evidence record")
    if evidence.get("force_push_performed") is not True:
        raise PurgeError("verify-origin requires completed origin force-update evidence")
    try:
        pre_manifest = _normalize_public_ref_entries(
            evidence["pre_rewrite_public_ref_manifest"]
        )
        post_manifest = _normalize_public_ref_entries(
            evidence["post_rewrite_public_ref_manifest"]
        )
        pre_snapshot = _snapshot_from_payload(evidence["pre_rewrite_snapshot"])
        backup_dir = _ensure_external_path(repository, evidence["backup_dir"], "backup destination")
        backup_mirror = _repository_root(backup_dir / "mirror")
    except (KeyError, TypeError, ValueError) as exc:
        raise PurgeError("apply evidence lacks exact verification inputs") from exc
    if tuple(name for name, _ in pre_manifest) != tuple(name for name, _ in post_manifest):
        raise PurgeError("apply evidence public ref names changed")
    candidate_verification = evidence.get("verification")
    if not isinstance(candidate_verification, dict):
        raise PurgeError("apply evidence lacks candidate verification")
    candidate_path = candidate_verification.get("verification_repo")
    if not isinstance(candidate_path, str) or not candidate_path.strip():
        raise PurgeError("apply evidence lacks candidate verification mirror")
    candidate_root = _ensure_external_path(
        repository,
        candidate_path,
        "candidate verification repository",
    )
    _assert_full_mirror(candidate_root)
    if public_ref_manifest(candidate_root) != post_manifest:
        raise PurgeError("apply candidate verification mirror ref OIDs changed")
    recorded_candidate_path = evidence.get("verification_repo")
    if not isinstance(recorded_candidate_path, str) or _resolve_path(recorded_candidate_path) != candidate_root:
        raise PurgeError("apply evidence candidate verification mirror is inconsistent")
    if snapshot_repository(backup_mirror) != pre_snapshot:
        raise PurgeError("backup mirror does not match the apply evidence")
    canonical_checker = Path(__file__).with_name("check_pii.py").resolve()
    try:
        checker_digest = hashlib.sha256(canonical_checker.read_bytes()).hexdigest()
    except OSError as exc:
        raise PurgeError("history guard script is unavailable") from exc
    if (
        evidence.get("check_pii_path") != str(canonical_checker)
        or evidence.get("check_pii_sha256") != checker_digest
    ):
        raise PurgeError("apply evidence check_pii.py identity is stale")
    authorization_file = (
        _ensure_external_path(repository, args.authorization_file, "authorization record")
        if args.authorization_file is not None
        else None
    )
    locator = _authorization_locator(
        authorization_file=authorization_file,
        authorization_comment_id=args.authorization_comment_id,
        authorization_comment_url=args.authorization_comment_url,
    )
    if locator is None or not authorization_matches(
        path=authorization_file,
        comment_id=args.authorization_comment_id,
        comment_url=args.authorization_comment_url,
    ):
        raise PurgeError("verified owner issue-comment authorization is required before origin verification")
    verification_root, origin_url = create_origin_verification_mirror(
        repository,
        args.verification_repo,
    )
    verification = verify_post_rewrite(
        verification_root,
        backup_mirror,
        pre_snapshot.commit_ids,
        check_pii_path=canonical_checker,
        expected_public_refs=pre_manifest,
        expected_post_public_refs=post_manifest,
    )
    actual_manifest = public_ref_manifest(verification_root)
    post_push = {
        "computed": True,
        "computed_by": "history_purge.verify_origin",
        "provenance": "canonical-origin-fresh-mirror",
        "fresh_clone": True,
        "verification_repo_kind": "full-mirror",
        "verification_repo": str(verification_root),
        "origin_url": origin_url,
        "history_guard_passed": verification.history_guard_passed,
        "original_commits_reachable": list(verification.original_commits_reachable),
        "fixture_projection_equal": verification.fixture_projection_equal,
        "public_refs_manifest_equal": verification.public_refs_manifest_equal,
        "public_ref_manifest": [list(item) for item in actual_manifest],
        "check_pii_sha256": checker_digest,
    }
    updated = dict(evidence)
    updated["post_push_verification"] = post_push
    write_evidence_record(evidence_path, updated, root=repository)
    print(
        json.dumps(
            {
                "mode": "verify-origin",
                "verification_repo": str(verification_root),
                "origin_url": origin_url,
                "public_refs_manifest_equal": verification.public_refs_manifest_equal,
                "remote_contacted": True,
                "evidence_path": str(evidence_path),
            },
            sort_keys=True,
        )
    )
    return 0




def _finalize(args: argparse.Namespace, repository: Path) -> int:
    if args.map_path is None:
        raise PurgeError("map finalization requires --map-path")
    if args.evidence_path is None:
        raise PurgeError("map finalization requires --evidence-path")
    evidence_path = finalize_map_deletion(
        repository,
        args.map_path,
        args.evidence_path,
    )
    print(
        json.dumps(
            {
                "mode": "finalize-map-deletion",
                "remote_contacted": False,
                "external_map_deleted": True,
                "evidence_path": str(evidence_path),
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repository = _repository_root(args.root)
        authorization_inputs = (
            args.authorization is not None
            or args.authorization_file is not None
            or args.authorization_comment_id is not None
            or args.authorization_comment_url is not None
        )
        authorization_locator_inputs = (
            args.authorization_file is not None
            or args.authorization_comment_id is not None
            or args.authorization_comment_url is not None
        )
        if args.dry_run:
            if authorization_inputs:
                raise PurgeError("authorization input is valid only for apply mode")
            if (
                args.backup_reviewed
                or args.evidence_path
                or args.verification_repo
                or args.check_pii
            ):
                raise PurgeError("apply-only options cannot be used with dry-run")
            return _dry_run(args, repository)
        if args.apply:
            return _apply(args, repository)
        if args.verify_origin:
            if (
                args.authorization is not None
                or not authorization_locator_inputs
                or args.map_path is not None
                or args.backup_reviewed
                or args.backup_dir
                or args.expected_inventory_count is not None
                or args.check_pii
            ):
                raise PurgeError(
                    "verify-origin requires one owner authorization comment locator "
                    "and rejects apply-only options"
                )
            return _verify_origin(args, repository)
        if (
            authorization_inputs
            or args.backup_reviewed
            or args.backup_dir
            or args.expected_inventory_count is not None
            or args.verification_repo
            or args.check_pii
        ):
            raise PurgeError("apply-only options cannot be used with map finalization")
        return _finalize(args, repository)
    except PurgeError as exc:
        print(f"history purge refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

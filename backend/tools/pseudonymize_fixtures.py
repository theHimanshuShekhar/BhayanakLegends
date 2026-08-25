"""Deterministically replace Riot identities in the tracked fixture corpus.

The replacement table is derived in memory from the input corpus and is never
written to disk. PUUID ordinals are assigned by raw-byte ordering so every
fixture and source reference gets the same stable synthetic identity.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

PUUID_KEYS = {"puuid"}
SYNTHETIC_PUUID = re.compile(r"(?:fixture|parity)-puuid-\d{2}")
SYNTHETIC_NAME = re.compile(r"FixturePlayer\d{2}")


def _is_raw_puuid(value: object) -> bool:
    return isinstance(value, str) and len(value) > 40 and not SYNTHETIC_PUUID.fullmatch(value)


def _walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (key,)
            yield child_path, key, child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (str(index),))


def _json_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_replacements(root: Path) -> dict[str, str]:
    """Build a corpus-wide raw-to-synthetic replacement table in memory."""
    documents = [(path, _load_json(path)) for path in _json_files(root)]
    puuids: set[str] = set()
    participants: list[tuple[str, dict[str, Any]]] = []
    for _, document in documents:
        for path, key, value in _walk(document):
            if key == "puuid" and _is_raw_puuid(value):
                puuids.add(value)
                parent: Any = document
                for component in path[:-1]:
                    parent = parent[int(component)] if isinstance(parent, list) else parent[component]
                if isinstance(parent, dict):
                    participants.append((value, parent))
            if key == "participants" and path[-2:] == ("metadata", "participants") and isinstance(value, list):
                puuids.update(item for item in value if _is_raw_puuid(item))

    ordinal = {puuid: index for index, puuid in enumerate(sorted(puuids, key=lambda item: item.encode()), 1)}
    replacements: dict[str, str] = {
        puuid: f"fixture-puuid-{number:02d}" for puuid, number in ordinal.items()
    }
    for puuid, participant in participants:
        number = ordinal[puuid]
        for key, replacement in (
            ("summonerId", f"fixture-summoner-{number:02d}"),
            ("riotIdGameName", f"FixturePlayer{number:02d}"),
            ("riotIdTagline", f"BL{number:02d}"),
        ):
            value = participant.get(key)
            if isinstance(value, str) and value:
                replacements[value] = replacement
        game_name = participant.get("riotIdGameName")
        tag_line = participant.get("riotIdTagline")
        if isinstance(game_name, str) and isinstance(tag_line, str) and game_name and tag_line:
            replacements[f"{game_name}#{tag_line}"] = f"FixturePlayer{number:02d}#BL{number:02d}"

    # LCU fixtures have names but no PUUID. Their deterministic participant
    # slots use the same synthetic name vocabulary as the Riot payload.
    for _, document in documents:
        for number, value in _identity_name_slots(document):
            if isinstance(value, str) and value and not SYNTHETIC_NAME.fullmatch(value):
                replacements.setdefault(value, f"FixturePlayer{number:02d}")
    return replacements


def _identity_name_slots(document: Any) -> Iterable[tuple[int, Any]]:
    if not isinstance(document, dict):
        return
    players = document.get("allPlayers")
    if isinstance(players, list):
        for index, player in enumerate(players, 1):
            if isinstance(player, dict) and "summonerName" in player:
                yield index, player["summonerName"]
    for team_name in ("myTeam", "theirTeam"):
        team = document.get(team_name)
        if isinstance(team, list):
            offset = 0 if team_name == "myTeam" else 5
            for index, player in enumerate(team, 1 + offset):
                if isinstance(player, dict) and "summonerName" in player:
                    yield index, player["summonerName"]


def _rewrite_fixture_fields(text: str, document: Any, replacements: dict[str, str]) -> str:
    """Rewrite repeated identity values by participant ordinal, not raw value."""
    ordered: dict[str, list[tuple[str, str]]] = {
        "summonerId": [],
        "riotIdGameName": [],
        "riotIdTagline": [],
    }
    for path, key, value in _walk(document):
        if key != "puuid" or not _is_raw_puuid(value):
            continue
        parent: Any = document
        for component in path[:-1]:
            parent = parent[int(component)] if isinstance(parent, list) else parent[component]
        if not isinstance(parent, dict):
            continue
        number_match = re.fullmatch(r"fixture-puuid-(\d{2})", replacements.get(value, ""))
        if number_match is None:
            continue
        number = int(number_match.group(1))
        for key_name, prefix in (
            ("summonerId", "fixture-summoner-"),
            ("riotIdGameName", "FixturePlayer"),
            ("riotIdTagline", "BL"),
        ):
            source = parent.get(key_name)
            if isinstance(source, str) and source:
                ordered[key_name].append((source, f"{prefix}{number:02d}"))

    for key, pairs in ordered.items():
        index = 0
        pattern = re.compile(rf'("{key}"\s*:\s*")([^"]*)(")')

        def replace(match: re.Match[str]) -> str:
            nonlocal index
            if index < len(pairs) and match.group(2) == pairs[index][0]:
                result = f"{match.group(1)}{pairs[index][1]}{match.group(3)}"
                index += 1
                return result
            return match.group(0)

        text = pattern.sub(replace, text)
    return text


def pseudonymize_text(text: str, replacements: dict[str, str]) -> str:
    """Apply safe global replacements without exposing source values."""
    for source in sorted(replacements, key=len, reverse=True):
        if len(source) >= 7:
            text = text.replace(source, replacements[source])
    return text


def pseudonymize_tree(root: Path, replacements: dict[str, str] | None = None) -> int:
    """Rewrite text files under ``root`` while preserving non-identity bytes."""
    fixture_root = root / "backend" / "tests" / "fixtures"
    replacements = replacements or build_replacements(fixture_root)
    changed = 0
    for path in _tracked_text_files(root):
        original = path.read_text(encoding="utf-8")
        rewritten = original
        if fixture_root in path.parents and path.suffix == ".json":
            rewritten = _rewrite_fixture_fields(rewritten, _load_json(path), replacements)
        rewritten = pseudonymize_text(rewritten, replacements)
        if rewritten != original:
            path.write_text(rewritten, encoding="utf-8")
            changed += 1
    return changed
def _tracked_text_files(root: Path) -> Iterable[Path]:
    git_dir = root / ".git"
    if git_dir.exists():
        names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
        candidates = [root / name for name in names.decode().split("\0") if name]
    else:
        candidates = sorted(path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts)
    for path in candidates:
        try:
            raw = path.read_bytes()
            raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--check", action="store_true", help="fail if any identity would be changed")
    args = parser.parse_args()
    replacements = build_replacements(args.root / "backend" / "tests" / "fixtures")
    if args.check:
        return int(any(
            pseudonymize_text(path.read_text(encoding="utf-8"), replacements) != path.read_text(encoding="utf-8")
            for path in _tracked_text_files(args.root)
        ))
    print(f"pseudonymized {pseudonymize_tree(args.root, replacements)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

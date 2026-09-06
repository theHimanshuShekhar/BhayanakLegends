"""Pure match-v5 extractors turning raw Riot JSON into Personal History rows."""

from __future__ import annotations

from typing import Any


def parse_match(detail: dict[str, Any], puuid: str) -> dict[str, Any]:
    """Extract the personal row for ``puuid`` from a match-v5 detail payload.

    ``patch`` is the first two components of ``gameVersion`` (e.g. "16.7"),
    matching the two-part patch labels used by the Findings Pack dataset.
    """
    info = detail["info"]
    me = _participant(info["participants"], puuid)
    version = str(info.get("gameVersion") or "")
    patch = ".".join(version.split(".")[:2]) or None
    position = (me.get("teamPosition") or "").upper() or None
    return {
        "match_id": str(detail["metadata"]["matchId"]),
        "played_at": _iso_utc(int(info["gameEndTimestamp"])),
        "patch": patch,
        "role": position,
        "champion": me.get("championName") or None,
        "win": bool(me.get("win")),
        "duration_s": int(info.get("gameDuration") or 0),
    }


def _participant(participants: list[dict[str, Any]], puuid: str) -> dict[str, Any]:
    for entry in participants:
        if entry.get("puuid") == puuid:
            return entry
    raise KeyError(f"puuid {puuid!r} not among participants")


def _iso_utc(epoch_ms: int) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_ms / 1000))

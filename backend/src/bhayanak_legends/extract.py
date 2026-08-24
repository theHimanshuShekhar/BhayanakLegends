"""Pure match-v5 extractors turning raw Riot JSON into Personal History rows."""

from __future__ import annotations

import statistics
from typing import Any

CHECKPOINT_MINUTES = (10, 15, 20)
FRAME_TOLERANCE_MS = 30_000


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


def parse_checkpoints(timeline: dict[str, Any] | None, puuid: str) -> dict[str, float | int | None]:
    """Per-minute checkpoints at 10/15/20 for ``puuid`` from a match timeline.

    gold_diff_X is a v1 proxy: the participant's totalGold at minute X minus
    the median totalGold of all ten participants in the same frame. True
    lane-opponent diffs are not derivable without position-aware frames and
    arrive with the loltrends timeline families (docs/adr/0001).
    cs10 is minionsKilled + jungleMinionsKilled at minute 10.
    Missing/short timelines yield None per key.
    """
    checkpoints: dict[str, float | int | None] = {}
    for minutes in CHECKPOINT_MINUTES:
        checkpoints[f"gold_diff_{minutes}"] = None
        if minutes == 10:
            checkpoints["cs10"] = None
            checkpoints["level10"] = None
    if not timeline:
        return checkpoints

    puuids = list(timeline.get("metadata", {}).get("participants", []))
    if puuid not in puuids:
        return checkpoints
    participant_id = puuids.index(puuid) + 1
    pid_key = str(participant_id)

    for minutes in CHECKPOINT_MINUTES:
        frame = _frame_at(timeline, minutes)
        if frame is None:
            continue
        frames_map = frame.get("participantFrames", {})
        mine = frames_map.get(pid_key)
        if mine is None:
            continue
        all_gold = [
            f.get("totalGold")
            for f in frames_map.values()
            if isinstance(f.get("totalGold"), (int, float))
        ]
        gold = mine.get("totalGold")
        checkpoints[f"gold_diff_{minutes}"] = (
            float(gold - statistics.median(all_gold)) if all_gold and isinstance(gold, (int, float)) else None
        )
        if minutes == 10:
            checkpoints["cs10"] = int(mine.get("minionsKilled") or 0) + int(
                mine.get("jungleMinionsKilled") or 0
            )
            checkpoints["level10"] = int(mine.get("level") or 0)
    return checkpoints


def _participant(participants: list[dict[str, Any]], puuid: str) -> dict[str, Any]:
    for entry in participants:
        if entry.get("puuid") == puuid:
            return entry
    raise KeyError(f"puuid {puuid!r} not among participants")


def _frame_at(timeline: dict[str, Any], minutes: int) -> dict[str, Any] | None:
    target_ms = minutes * 60_000
    best: tuple[int, dict[str, Any]] | None = None
    for frame in timeline.get("info", {}).get("frames", []):
        ts = frame.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        delta = abs(int(ts) - target_ms)
        if delta <= FRAME_TOLERANCE_MS and (best is None or delta < best[0]):
            best = (delta, frame)
    return best[1] if best else None


def _iso_utc(epoch_ms: int) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_ms / 1000))

#!/usr/bin/env python3
"""Deterministic local LCU and Live Client Data replay services for Playwright."""
from __future__ import annotations

import argparse
import json
import sqlite3
import signal
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LCU_FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "lcu"


def load_json(name: str) -> dict:
    return json.loads((LCU_FIXTURES / name).read_text(encoding="utf-8"))


class ReplayState:
    def __init__(self, kind: str, data_dir: Path | None = None) -> None:
        self.kind = kind
        self.data_dir = data_dir
        self.scenario = "idle"
        self._phase_generation = 0
        self.champ = load_json("champselect_session.json")
        self.game = load_json("allgamedata.json")

    @staticmethod
    def _gameflow_for(scenario: str) -> str:
        if scenario in {
            "champ-select",
            "champ-select-update",
            "champ-select-assigned",
            "champ-select-assigned-unlocked",
            "champ-select-picked",
            "champ-select-picked-not-locked",
            "champ-select-locked",
            "champ-select-completed-lock",
            "champ-select-unknown-role",
            "champ-select-unknown",
            "pack-unavailable",
            "pack-error",
        }:
            return "ChampSelect"
        if scenario in {"in-game", "in-game-pre-event", "in-game-update", "in-game-empty", "malformed"}:
            return "InProgress"
        return "None"

    def _refresh_live_observation(self) -> None:
        self.game["observed_at_s"] = time.time()
        # The real Live Client API has no replay marker. This fixture-only
        # field makes an explicit phase transition a new local observation
        # for the production provider's frozen-stream fingerprint.
        self.game["replay_phase_generation"] = self._phase_generation
    def set_history_latest(self, eligibility: str) -> None:
        if self.kind != "lcu" or self.data_dir is None:
            raise ValueError("history seed control is available only on the owned LCU replay")
        if eligibility not in {"eligible", "ineligible"}:
            raise ValueError(f"unknown history eligibility: {eligibility}")
        if eligibility == "eligible":
            eligible_played_at = "2026-03-01T00:00:00Z"
            ineligible_played_at = "2026-02-01T00:00:00Z"
        else:
            eligible_played_at = "2026-02-01T00:00:00Z"
            ineligible_played_at = "2026-03-01T00:00:00Z"
        with sqlite3.connect(self.data_dir / "app.db", timeout=5.0) as connection:
            connection.execute(
                "UPDATE matches SET played_at = ? WHERE match_id = ?",
                (eligible_played_at, "what-if-eligible"),
            )
            connection.execute(
                "UPDATE matches SET played_at = ? WHERE match_id = ?",
                (ineligible_played_at, "what-if-ineligible"),
            )


    def _local_cell(self) -> dict:
        local_cell_id = self.champ["localTeamCellId"]
        return next(player for player in self.champ["myTeam"] if player["cellId"] == local_cell_id)

    def _set_local_state(
        self,
        *,
        assigned_position: object,
        champion_id: int,
        completed: bool,
    ) -> None:
        local = self._local_cell()
        local["assignedPosition"] = assigned_position
        local["championId"] = champion_id
        local["championPickIntent"] = champion_id
        self.champ["actions"] = [
            [
                {
                    "actorCellId": self.champ["localTeamCellId"],
                    "championId": champion_id,
                    "completed": completed,
                    "type": "pick",
                }
            ]
        ]

    def set_scenario(self, scenario: str) -> None:
        scenario = {
            "assigned-unlocked": "champ-select-assigned-unlocked",
            "picked-not-locked": "champ-select-picked-not-locked",
            "completed-lock": "champ-select-completed-lock",
            "unknown-role": "champ-select-unknown-role",
            "missing-pack": "pack-unavailable",
        }.get(scenario, scenario)
        previous_phase = self._gameflow_for(self.scenario)
        next_phase = self._gameflow_for(scenario)
        if next_phase != previous_phase:
            self._phase_generation += 1
        self.scenario = scenario
        if scenario in {"champ-select", "champ-select-locked", "champ-select-completed-lock"}:
            self.champ = load_json("champselect_session.json")
            if scenario != "champ-select":
                self._set_local_state(assigned_position="middle", champion_id=1, completed=True)
        elif scenario in {"champ-select-update", "champ-select-picked", "champ-select-picked-not-locked"}:
            self.champ = load_json("champselect_session.json")
            if scenario == "champ-select-update":
                self.champ["timer"]["adjustedTimeLeftInSec"] = 11
                self._set_local_state(assigned_position="top", champion_id=25, completed=False)
            else:
                self._set_local_state(assigned_position="top", champion_id=1, completed=False)
        elif scenario in {"champ-select-assigned", "champ-select-assigned-unlocked"}:
            self.champ = load_json("champselect_session.json")
            self._set_local_state(assigned_position="top", champion_id=0, completed=False)
        elif scenario in {"champ-select-unknown-role", "champ-select-unknown"}:
            self.champ = load_json("champselect_session.json")
            self._set_local_state(assigned_position="UNKNOWN", champion_id=0, completed=False)
        elif scenario == "in-game-empty":
            self.game = load_json("allgamedata.json")
            self._refresh_live_observation()
            for player in self.game["allPlayers"]:
                player["items"] = []
            self.game["events"]["Events"] = []
        elif scenario in {"in-game", "in-game-pre-event", "in-game-update"}:
            self.game = load_json("allgamedata.json")
            self._refresh_live_observation()
            if scenario == "in-game-pre-event":
                self.game["gameData"]["gameTime"] = 780.0
            elif scenario == "in-game-update":
                self.game["gameData"]["gameTime"] = 812.4
                self.game["gameData"]["gameId"] = 5123456789
                self.game["events"]["Events"].append(
                    {
                        "EventName": "BaronKill",
                        "EventTime": 801.2,
                        "KillerName": "Order",
                        "DragonType": None,
                    }
                )
                player = next(p for p in self.game["allPlayers"] if p["summonerName"] == "FixturePlayer03")
                player["scores"]["kills"] = 5
        elif scenario in {"pack-unavailable", "pack-error"}:
            self.champ = load_json("champselect_session.json")
            self._set_local_state(assigned_position="top", champion_id=0, completed=False)
        elif scenario in {"idle", "reconnect", "malformed"}:
            return
        else:
            raise ValueError(f"unknown replay scenario: {scenario}")

    def gameflow(self) -> str:
        if self.scenario in {
            "champ-select",
            "champ-select-update",
            "champ-select-assigned",
            "champ-select-assigned-unlocked",
            "champ-select-picked",
            "champ-select-picked-not-locked",
            "champ-select-locked",
            "champ-select-completed-lock",
            "champ-select-unknown-role",
            "champ-select-unknown",
            "pack-unavailable",
            "pack-error",
        }:
            return "ChampSelect"
        if self.scenario in {"in-game", "in-game-update", "in-game-empty", "malformed"}:
            return "InProgress"
        return "None"

    def response(self, path: str) -> tuple[int, object]:
        if self.scenario == "malformed" and path != "phase":
            return 200, "{malformed"
        if self.kind == "lcu":
            if path == "phase":
                return 200, self._gameflow_for(self.scenario)
            if path == "session":
                return 200, self.champ if self.scenario.startswith("champ-select") else None
            if path == "summoner":
                return 200, {"summonerId": "replay"}
        else:
            if path == "allgamedata":
                if self.scenario.startswith("in-game"):
                    self._refresh_live_observation()
                    return 200, self.game
                return 200, None
        return 404, {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    server_version = "BhayanakReplay/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    @property
    def replay(self) -> ReplayState:
        return self.server.replay  # type: ignore[attr-defined]

    def _send(self, status: int, payload: object) -> None:
        if isinstance(payload, str):
            body = payload.encode("utf-8")
            content_type = "text/plain"
        else:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            content_type = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, {"status": "ok", "kind": self.replay.kind, "scenario": self.replay.scenario})
            return
        routes = {
            "/lol-gameflow/v1/gameflow-phase": "phase",
            "/lol-champ-select/v1/session": "session",
            "/lol-summoner/v1/current-summoner": "summoner",
            "/liveclientdata/allgamedata": "allgamedata",
        }
        route = routes.get(path)
        if route is None:
            self._send(404, {"error": "not found"})
            return
        status, payload = self.replay.response(route)
        self._send(status, payload)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/control":
            self._send(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size) or b"{}")
            scenario = str(payload["scenario"])
            if scenario.startswith("history-"):
                self.replay.set_history_latest(scenario.removeprefix("history-"))
                self._send(200, {"status": "ok", "scenario": scenario})
                return
            self.replay.set_scenario(scenario)
        except (ValueError, KeyError, json.JSONDecodeError, sqlite3.Error) as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(200, {"status": "ok", "scenario": self.replay.scenario})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("lcu", "live"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    state = ReplayState(args.kind, args.data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.replay = state  # type: ignore[attr-defined]
    server.daemon_threads = True

    def stop(_signum: int, _frame: object) -> None:
        import threading

        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGINT, stop)
    print(json.dumps({"type": "ready", "kind": args.kind, "port": args.port}), flush=True)
    server.serve_forever(poll_interval=0.05)
    server.server_close()


if __name__ == "__main__":
    main()

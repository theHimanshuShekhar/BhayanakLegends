#!/usr/bin/env python3
"""Deterministic local LCU and Live Client Data replay services for Playwright."""
from __future__ import annotations

import argparse
import copy
import json
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LCU_FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "lcu"


def load_json(name: str) -> dict:
    return json.loads((LCU_FIXTURES / name).read_text(encoding="utf-8"))


class ReplayState:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.scenario = "idle"
        self.champ = load_json("champselect_session.json")
        self.game = load_json("allgamedata.json")

    def set_scenario(self, scenario: str) -> None:
        self.scenario = scenario
        if scenario == "champ-select":
            self.champ = load_json("champselect_session.json")
        elif scenario == "champ-select-update":
            self.champ = load_json("champselect_session.json")
            self.champ["timer"]["adjustedTimeLeftInSec"] = 11
            local = next(p for p in self.champ["myTeam"] if p["cellId"] == 2)
            local["championId"] = 25
            local["championPickIntent"] = 25
        elif scenario == "in-game":
            self.game = load_json("allgamedata.json")
        elif scenario == "in-game-update":
            self.game = load_json("allgamedata.json")
            self.game["gameData"]["gameTime"] = 812.4
            self.game["gameData"]["gameId"] = 5123456790
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
        elif scenario in {"idle", "reconnect", "malformed"}:
            return
        else:
            raise ValueError(f"unknown replay scenario: {scenario}")

    def gameflow(self) -> str:
        if self.scenario in {"champ-select", "champ-select-update"}:
            return "ChampSelect"
        if self.scenario in {"in-game", "in-game-update", "malformed"}:
            return "InProgress"
        return "None"

    def response(self, path: str) -> tuple[int, object]:
        if self.scenario == "malformed" and path != "phase":
            return 200, "{malformed"
        if self.kind == "lcu":
            if path == "phase":
                return 200, self.gameflow()
            if path == "session":
                return 200, self.champ if self.scenario.startswith("champ-select") else None
            if path == "summoner":
                return 200, {"summonerId": "replay"}
        else:
            if path == "allgamedata":
                return 200, self.game if self.scenario.startswith("in-game") else None
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
            self.replay.set_scenario(str(payload["scenario"]))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(200, {"status": "ok", "scenario": self.replay.scenario})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("lcu", "live"), required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    state = ReplayState(args.kind)
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

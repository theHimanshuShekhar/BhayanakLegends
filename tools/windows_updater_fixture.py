"""Serve a deterministic, loopback-only updater fixture for the Windows smoke.

The first latest.json request is a valid no-update response. Later checks expose an
update whose artifact has an intentionally invalid signature. No request can leave
127.0.0.1, and every request is recorded as a path-only diagnostic.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

CURRENT_VERSION = "0.1.0"
UPDATE_VERSION = "0.1.1"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    requests_file = args.state_file.with_suffix(".requests.jsonl")

    class FixtureHandler(BaseHTTPRequestHandler):
        latest_requests = 0

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            with requests_file.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"method": "GET", "path": parsed.path}) + "\n")

            if parsed.path == "/latest.json":
                FixtureHandler.latest_requests += 1
                if FixtureHandler.latest_requests == 1:
                    payload = {
                        "version": CURRENT_VERSION,
                        "notes": "Windows smoke no-update fixture",
                        "pub_date": "2026-01-01T00:00:00Z",
                        "platforms": {
                            "windows-x86_64": {
                                "signature": "d2luZG93cy1zbW9rZS1ub19jaGFuZ2U=",
                                "url": f"http://127.0.0.1:{self.server.server_port}/artifact.bin",
                            }
                        },
                    }
                else:
                    payload = {
                        "version": UPDATE_VERSION,
                        "notes": "Windows smoke invalid-signature fixture",
                        "pub_date": "2026-01-01T00:00:00Z",
                        "platforms": {
                            "windows-x86_64": {
                                "signature": "d2luZG93cy1zbW9rZS1pbnZhbGlkLXNpZ25hdHVyZQ==",
                                "url": f"http://127.0.0.1:{self.server.server_port}/artifact.bin",
                            }
                        },
                    }
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/artifact.bin":
                body = b"not-a-real-update"
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), FixtureHandler)
    write_json(
        args.state_file,
        {
            "host": "127.0.0.1",
            "port": server.server_port,
            "requests_file": str(requests_file),
        },
    )
    print(f"fixture listening on 127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

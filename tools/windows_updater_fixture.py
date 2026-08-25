"""Serve a deterministic, loopback-only updater fixture for the Windows smoke.

The first latest.json request is a valid no-update response. Later checks expose an
update whose artifact has an intentionally invalid signature. The fixture also
serves a valid Findings Pack release used to prove durable activation. No request
can leave 127.0.0.1, and every request is recorded as a path-only diagnostic.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

CURRENT_VERSION = "0.1.0"
UPDATE_VERSION = "0.1.1"
PACK_VERSION = "v2-smoke"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def pack_asset() -> bytes:
    root = Path(__file__).resolve().parents[1] / "pack"
    pack = json.loads((root / "findings-pack.v1.json").read_text(encoding="utf-8"))
    pack["pack_version"] = PACK_VERSION
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("findings-pack.v1.json", json.dumps(pack))
        archive.writestr("pack.schema.json", (root / "pack.schema.json").read_bytes())
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    requests_file = args.state_file.with_suffix(".requests.jsonl")
    pack_bytes = pack_asset()
    pack_sha256 = hashlib.sha256(pack_bytes).hexdigest()

    class FixtureHandler(BaseHTTPRequestHandler):
        latest_requests = 0

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            with requests_file.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"method": "GET", "path": parsed.path}) + "\n")

            if parsed.path == "/findings-pack-manifest.json":
                payload = {
                    "pack_version": PACK_VERSION,
                    "schema_version": 1,
                    "feature_contract_version": "loltrends-parity-v1",
                    "download_url": f"http://127.0.0.1:{self.server.server_port}/findings-pack.zip",
                    "sha256": pack_sha256,
                    "size": len(pack_bytes),
                    "required_model_artifacts": [],
                }
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/findings-pack.zip":
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(pack_bytes)))
                self.end_headers()
                self.wfile.write(pack_bytes)
                return

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

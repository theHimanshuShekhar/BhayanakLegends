"""Serve a deterministic, loopback-only updater fixture for the Windows smoke.

Phase sequence, driven entirely by request order plus an on-disk flip file:

1. The first ``/latest.json`` check offers a real higher-version updater whose
   metadata carries the detached signature emitted next to the real archive;
   ``/updater/update.bin`` then serves those exact archive bytes.
2. Once the valid archive has been served once, further checks advertise the
   installed (updated) version so the relaunched app observes "up to date".
3. When the harness creates the flip file, checks offer a higher rejected
   version whose signature deliberately does not match the served bytes;
   ``/updater/rejected.bin`` returns the same real archive bytes so the only
   possible failure is signature verification.

The fixture also serves a valid Findings Pack release used to prove durable
activation. Every request is recorded as a path-only diagnostic line and no
request can leave 127.0.0.1: the socket binds the loopback interface only.
Artifact paths, signature paths, and versions are passed explicitly so a fake
artifact can never be mistaken for a valid update.

``tauri signer`` writes private keys, public keys, and detached signatures as
a single line of base64 text (the base64 encoding of the classic minisign
armored comment+key block). That text is already the exact value the updater
plugin expects in ``latest.json``'s ``signature`` field and in
``tauri.conf.json``'s ``pubkey`` field, so this fixture copies signature file
contents verbatim rather than re-encoding them.
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

UPDATE_ARTIFACT_PATH = "/updater/update.bin"
REJECTED_ARTIFACT_PATH = "/updater/rejected.bin"
PACK_VERSION = "v2-smoke"
PUB_DATE = "2026-01-01T00:00:00Z"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_bytes(path: Path, label: str) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"{label} is unreadable: {path} ({exc})") from exc
    if not data:
        raise SystemExit(f"{label} is empty: {path}")
    return data


def read_text(path: Path, label: str) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"{label} is unreadable: {path} ({exc})") from exc
    if not text:
        raise SystemExit(f"{label} is empty: {path}")
    return text


def pack_asset(pack_root: Path) -> bytes:
    pack = json.loads((pack_root / "findings-pack.v1.json").read_text(encoding="utf-8"))
    pack["pack_version"] = PACK_VERSION
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("findings-pack.v1.json", json.dumps(pack))
        archive.writestr("pack.schema.json", (pack_root / "pack.schema.json").read_bytes())
    return output.getvalue()


class FixtureConfig:
    """Validated fixture inputs shared with the request handler."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.update_version = args.update_version
        self.rejected_version = args.rejected_version
        self.artifact = read_bytes(args.artifact, "updater artifact")
        self.signature = read_text(args.signature, "detached signature")
        self.rejected_signature = read_text(args.rejected_signature, "rejected signature")
        if self.rejected_signature == self.signature:
            raise SystemExit(
                "rejected signature must differ from the valid signature; "
                "sign different bytes with the ephemeral key"
            )
        if self.update_version == self.rejected_version:
            raise SystemExit("rejected version must differ from the update version")
        self.flip_file = args.flip_file
        self.requests_file = args.state_file.with_suffix(".requests.jsonl")
        self.pack_root = args.pack_root


class FixtureState:
    """Request-order state machine shared across handler threads."""

    def __init__(self) -> None:
        self.latest_requests = 0
        self.valid_artifact_served = False


def make_handler(
    config: FixtureConfig, state: FixtureState
) -> type[BaseHTTPRequestHandler]:
    pack_bytes = pack_asset(config.pack_root)
    pack_sha256 = hashlib.sha256(pack_bytes).hexdigest()

    class FixtureHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: object) -> None:
            self._send(json.dumps(payload).encode("utf-8"), "application/json")

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            # Path-only diagnostics: query strings are stripped before logging.
            with config.requests_file.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"method": "GET", "path": parsed.path}) + "\n")

            if parsed.path == "/findings-pack-manifest.json":
                self._send_json(
                    {
                        "pack_version": PACK_VERSION,
                        "schema_version": 1,
                        "feature_contract_version": "loltrends-parity-v1",
                        "download_url": f"http://127.0.0.1:{self.server.server_port}/findings-pack.zip",
                        "sha256": pack_sha256,
                        "size": len(pack_bytes),
                        "required_model_artifacts": [],
                    }
                )
                return

            if parsed.path == "/findings-pack.zip":
                self._send(pack_bytes, "application/zip")
                return

            if parsed.path == UPDATE_ARTIFACT_PATH:
                state.valid_artifact_served = True
                self._send(config.artifact, "application/octet-stream")
                return

            if parsed.path == REJECTED_ARTIFACT_PATH:
                # Same real archive bytes; only the signature differs, so any
                # rejection below is attributable to verification alone.
                self._send(config.artifact, "application/octet-stream")
                return

            if parsed.path == "/latest.json":
                self._send_json(self._latest_payload())
                return

            self.send_error(404)

        def _latest_payload(self) -> object:
            base = f"http://127.0.0.1:{self.server.server_port}"
            state.latest_requests += 1
            if config.flip_file.exists():
                return {
                    "version": config.rejected_version,
                    "notes": "Windows smoke mismatched-signature fixture",
                    "pub_date": PUB_DATE,
                    "platforms": {
                        "windows-x86_64": {
                            "signature": config.rejected_signature,
                            "url": f"{base}{REJECTED_ARTIFACT_PATH}",
                        }
                    },
                }
            if not state.valid_artifact_served:
                return {
                    "version": config.update_version,
                    "notes": "Windows smoke valid signed update",
                    "pub_date": PUB_DATE,
                    "platforms": {
                        "windows-x86_64": {
                            "signature": config.signature,
                            "url": f"{base}{UPDATE_ARTIFACT_PATH}",
                        }
                    },
                }
            return {
                "version": config.update_version,
                "notes": "Windows smoke up-to-date fixture",
                "pub_date": PUB_DATE,
                "platforms": {
                    "windows-x86_64": {
                        "signature": config.signature,
                        "url": f"{base}{UPDATE_ARTIFACT_PATH}",
                    }
                },
            }

    return FixtureHandler


def build_server(config: FixtureConfig, port: int) -> tuple[ThreadingHTTPServer, FixtureState]:
    state = FixtureState()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(config, state))
    return server, state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--update-version", required=True)
    parser.add_argument("--rejected-version", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--rejected-signature", required=True, type=Path)
    parser.add_argument(
        "--flip-file",
        required=True,
        type=Path,
        help="harness creates this file to switch latest.json to the rejected offer",
    )
    parser.add_argument(
        "--pack-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "pack",
    )
    args = parser.parse_args()

    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    config = FixtureConfig(args)
    server, _state = build_server(config, args.port)
    write_json(
        args.state_file,
        {
            "host": "127.0.0.1",
            "port": server.server_port,
            "requests_file": str(config.requests_file),
        },
    )
    print(f"fixture listening on 127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

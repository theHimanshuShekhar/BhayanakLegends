"""Serve real signed updater and Findings Pack assets to Windows smoke.

The fixture deliberately has two updater phases. The first ``latest.json``
response advertises the supplied higher-version archive and its emitted
detached signature. Every later response advertises a second higher version
whose supplied artifact/signature pair is known to be mismatched. It also
serves a canonical Findings Pack asset with an ephemeral detached Ed25519
manifest signature. The server binds only to the literal loopback address and
writes path-only request diagnostics.
"""

import argparse
import base64
import hashlib
import io
import json
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PACK_VERSION = "v2-smoke"
VALID_ARTIFACT_PREFIX = "/artifacts/valid/"
INVALID_ARTIFACT_PREFIX = "/artifacts/invalid/"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def pack_asset(pack_dir: Path) -> bytes:
    pack_path = pack_dir / "findings-pack.v2.json"
    if not pack_path.is_file():
        raise SystemExit(f"canonical Findings Pack v2 JSON is missing in {pack_dir}")
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        schema = (pack_dir / "pack.schema.json").read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"canonical Findings Pack v2 cannot be read from {pack_dir}") from exc
    pack["pack_version"] = PACK_VERSION
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("findings-pack.v2.json", json.dumps(pack))
        archive.writestr("pack.schema.json", schema)
    return output.getvalue()


def _read_artifact(path: Path, label: str) -> bytes:
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"{label} artifact cannot be read: {path}") from exc
    if not value:
        raise SystemExit(f"{label} artifact is empty: {path}")
    return value


def _read_signature(path: Path, label: str) -> str:
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"{label} updater signature cannot be read: {path}") from exc
    if not value.strip():
        raise SystemExit(f"{label} updater signature is empty: {path}")
    return value


def _artifact_route(prefix: str, name: str) -> str:
    return f"{prefix}{quote(name, safe='')}"


def _metadata(
    *,
    version: str,
    signature: str,
    route: str,
    port: int,
    notes: str,
) -> dict[str, object]:
    return {
        "version": version,
        "notes": notes,
        "pub_date": "2026-01-01T00:00:00Z",
        "platforms": {
            "windows-x86_64": {
                "signature": signature,
                "url": f"http://127.0.0.1:{port}{route}",
            }
        },
    }


def _send_bytes(handler: BaseHTTPRequestHandler, body: bytes, content_type: str) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--pack-dir", type=Path)
    parser.add_argument("--current-version", required=True)
    parser.add_argument("--valid-version", required=True)
    parser.add_argument("--valid-artifact", required=True, type=Path)
    parser.add_argument("--valid-signature", required=True, type=Path)
    parser.add_argument("--invalid-version", required=True)
    parser.add_argument("--invalid-artifact", required=True, type=Path)
    parser.add_argument("--invalid-signature", required=True, type=Path)
    parser.add_argument("--flip-file", type=Path)
    args = parser.parse_args()

    if args.current_version == args.valid_version:
        raise SystemExit("current and valid updater versions must differ")
    if args.valid_version == args.invalid_version:
        raise SystemExit("valid and invalid updater versions must differ")

    valid_artifact = _read_artifact(args.valid_artifact, "valid")
    valid_signature = _read_signature(args.valid_signature, "valid")
    invalid_artifact = _read_artifact(args.invalid_artifact, "invalid")
    invalid_signature = _read_signature(args.invalid_signature, "invalid")
    if valid_artifact == invalid_artifact and valid_signature == invalid_signature:
        raise SystemExit("invalid updater inputs must not repeat the valid artifact/signature pair")
    requests_file = args.state_file.with_suffix(".requests.jsonl")
    pack_dir = args.pack_dir or Path(__file__).resolve().parents[1] / "pack"
    pack_bytes = pack_asset(pack_dir)
    pack_sha256 = hashlib.sha256(pack_bytes).hexdigest()
    valid_route = _artifact_route(VALID_ARTIFACT_PREFIX, args.valid_artifact.name)
    invalid_route = _artifact_route(INVALID_ARTIFACT_PREFIX, args.invalid_artifact.name)

    class FixtureHandler(BaseHTTPRequestHandler):
        latest_requests = 0
        valid_artifact_served = False
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _reject(self, message: str) -> None:
            body = f"{message}\n".encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _validate_loopback_request(self) -> str | None:
            host = self.headers.get("Host")
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if host not in {"127.0.0.1", expected_host}:
                self._reject("fixture accepts only literal 127.0.0.1")
                return None

            parsed = urlparse(self.path)
            if parsed.scheme or parsed.netloc:
                self._reject("fixture accepts origin-form request paths only")
                return None
            if parsed.query or parsed.fragment:
                self._reject("fixture does not accept query-bearing updater requests")
                return None
            return parsed.path

        def _record(self, path: str) -> None:
            with requests_file.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"method": "GET", "path": path}) + "\n")

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = self._validate_loopback_request()
            if path is None:
                return
            self._record(path)

            if path == "/findings-pack-manifest.json":
                _send_bytes(self, manifest_bytes, "application/json")
                return

            if path == "/findings-pack-manifest.json.sig":
                _send_bytes(self, manifest_signature, "text/plain; charset=utf-8")
                return

            if path == "/findings-pack.zip":
                _send_bytes(self, pack_bytes, "application/zip")
                return

            if path == "/latest.json":
                FixtureHandler.latest_requests += 1
                if (args.flip_file is None and FixtureHandler.valid_artifact_served) or (
                    args.flip_file is not None and args.flip_file.exists()
                ):
                    payload = _metadata(
                        version=args.invalid_version,
                        signature=invalid_signature,
                        route=invalid_route,
                        port=self.server.server_port,
                        notes="Windows smoke mismatched-signature updater fixture",
                    )
                else:
                    payload = _metadata(
                        version=args.valid_version,
                        signature=valid_signature,
                        route=valid_route,
                        port=self.server.server_port,
                        notes=(
                            "Windows smoke valid signed updater fixture"
                            if not FixtureHandler.valid_artifact_served
                            else "Windows smoke up-to-date fixture"
                        ),
                    )
                _send_bytes(
                    self,
                    json.dumps(payload).encode("utf-8"),
                    "application/json",
                )
                return

            if path == valid_route:
                FixtureHandler.valid_artifact_served = True
                _send_bytes(self, valid_artifact, "application/octet-stream")
                return

            if path == invalid_route:
                _send_bytes(self, invalid_artifact, "application/octet-stream")
                return

            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), FixtureHandler)
    manifest_payload = {
        "pack_version": PACK_VERSION,
        "schema_version": 2,
        "feature_contract_versions": {
            "population": "loltrends-population-v2",
            "personal_history": "loltrends-parity-v2",
        },
        "feature_contract_version": "loltrends-population-v2",
        "download_url": f"http://127.0.0.1:{server.server_port}/findings-pack.zip",
        "sha256": pack_sha256,
        "size": len(pack_bytes),
        "required_model_artifacts": [],
    }
    manifest_bytes = json.dumps(
        manifest_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_private_key = Ed25519PrivateKey.generate()
    manifest_signature = base64.b64encode(
        manifest_private_key.sign(manifest_bytes)
    ) + b"\n"
    manifest_public_key = base64.b64encode(
        manifest_private_key.public_key().public_bytes_raw()
    ).decode("ascii")
    write_json(
        args.state_file,
        {
            "host": "127.0.0.1",
            "port": server.server_port,
            "requests_file": str(requests_file),
            "manifest_public_key": manifest_public_key,
            "manifest_signature_sha256": hashlib.sha256(manifest_signature).hexdigest(),
            "valid": {
                "version": args.valid_version,
                "artifact_name": args.valid_artifact.name,
                "artifact_route": valid_route,
                "artifact_sha256": hashlib.sha256(valid_artifact).hexdigest(),
                "signature_sha256": hashlib.sha256(valid_signature.encode("utf-8")).hexdigest(),
            },
            "invalid": {
                "version": args.invalid_version,
                "artifact_name": args.invalid_artifact.name,
                "artifact_route": invalid_route,
                "artifact_sha256": hashlib.sha256(invalid_artifact).hexdigest(),
                "signature_sha256": hashlib.sha256(invalid_signature.encode("utf-8")).hexdigest(),
            },
        },
    )
    print(f"fixture listening on 127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

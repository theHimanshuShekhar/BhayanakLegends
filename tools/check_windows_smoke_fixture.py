"""Assert the packaged smoke used the signed local updater fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def _read_rows(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"fixture request log cannot be read: {path}") from exc
    rows: list[dict[str, object]] = []
    for line in lines:
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit("fixture request log contains invalid JSON") from exc
        if not isinstance(row, dict):
            raise SystemExit("fixture request log rows must be objects")
        if set(row) != {"method", "path"} or row.get("method") != "GET":
            raise SystemExit("fixture diagnostics must contain only GET method and path")
        path_value = row.get("path")
        if not isinstance(path_value, str):
            raise SystemExit("fixture diagnostic path must be a string")
        parsed = urlsplit(path_value)
        if (
            not path_value.startswith("/")
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise SystemExit("fixture diagnostics must contain path-only loopback requests")
        rows.append(row)
    return rows


def _state_routes(path: Path) -> tuple[set[str], dict[str, str]]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"fixture state cannot be read: {path}") from exc
    if not isinstance(state, dict):
        raise SystemExit("fixture state must be an object")
    routes: set[str] = set()
    for phase in ("valid", "invalid"):
        value = state.get(phase)
        if not isinstance(value, dict) or not isinstance(value.get("artifact_route"), str):
            raise SystemExit(f"fixture state is missing the {phase} artifact route")
        routes.add(value["artifact_route"])
    if state.get("pack_version") != "v4":
        raise SystemExit("fixture canonical pack version must remain v4")
    corrupt_version = state.get("corrupt_manifest_pack_version")
    if corrupt_version != "v5-smoke-invalid-129":
        raise SystemExit("fixture corrupt manifest must use the smoke-only newer version")
    invalid = state.get("invalid")
    if not isinstance(invalid, dict):
        raise SystemExit("fixture state is missing invalid updater metadata")
    if invalid.get("artifact_bytes_differ") is not True:
        raise SystemExit("fixture invalid updater bytes must differ from the valid artifact")
    if invalid.get("signature_reused") is not True:
        raise SystemExit("fixture invalid updater must reuse the valid detached signature")
    findings_pack = state.get("findings_pack")
    required = (
        "valid_manifest_route",
        "corrupt_manifest_route",
        "valid_route",
        "corrupt_route",
    )
    if not isinstance(findings_pack, dict) or any(
        not isinstance(findings_pack.get(key), str) for key in required
    ):
        raise SystemExit("fixture state is missing Findings Pack rollback routes")
    return routes, {key: str(findings_pack[key]) for key in required}


def _check_security_proofs(path: Path) -> None:
    required_phases = {"update-available", "updated", "invalid"}
    found_phases: set[str] = set()
    for phase in sorted(required_phases):
        proof_path = path / f"sidecar-security-{phase}.json"
        try:
            text = proof_path.read_text(encoding="utf-8")
            proof = json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"sidecar security proof cannot be read: {proof_path}") from exc
        if not isinstance(proof, dict) or set(proof) != {"phase", "token", "http", "sse", "dev_import"}:
            raise SystemExit("sidecar security proof shape is invalid")
        if proof.get("phase") != phase:
            raise SystemExit("sidecar security proof phase does not match its filename")
        token = proof.get("token")
        if not isinstance(token, dict) or set(token) != {"length", "not_dev", "explicit"}:
            raise SystemExit("sidecar security proof must not contain raw token material")
        if not isinstance(token.get("length"), int) or token["length"] < 32:
            raise SystemExit("sidecar security proof token length is invalid")
        if token.get("not_dev") is not True or token.get("explicit") is not True:
            raise SystemExit("sidecar security proof token policy failed")
        http_rows = proof.get("http")
        expected_http = {
            "valid-token-valid-host": 200,
            "invalid-token-valid-host": 401,
            "valid-token-invalid-host": 400,
            "invalid-token-invalid-host": 400,
        }
        if not isinstance(http_rows, list) or {
            row.get("case"): row.get("status")
            for row in http_rows
            if isinstance(row, dict)
        } != expected_http:
            raise SystemExit("sidecar security HTTP matrix is incomplete or incorrect")
        sse = proof.get("sse")
        if sse != {"status": 200, "hello": True, "query_token": True}:
            raise SystemExit("sidecar security SSE query-token proof is missing")
        dev_import = proof.get("dev_import")
        if dev_import != {"status": 403, "fixture_reads": False}:
            raise SystemExit("sidecar frozen import proof is missing")
        if "/events?" in text or "token=" in text:
            raise SystemExit("sidecar security proof contains a raw query")
        found_phases.add(phase)
    if found_phases != required_phases:
        raise SystemExit("sidecar security proof is missing one or more phases")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("requests_file", type=Path)
    parser.add_argument("--smoke-state", type=Path)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--require-security", action="store_true")
    args = parser.parse_args()

    rows = _read_rows(args.requests_file)
    paths = [str(row["path"]) for row in rows]
    latest_indices = [index for index, path in enumerate(paths) if path == "/latest.json"]
    if not latest_indices:
        raise SystemExit(
            "packaged smoke must request updater metadata before and after the valid artifact"
        )
    valid_routes = [path for path in paths if path.startswith("/artifacts/valid/")]
    invalid_routes = [path for path in paths if path.startswith("/artifacts/invalid/")]
    if not valid_routes:
        raise SystemExit("packaged smoke did not download the real valid updater artifact")
    if not invalid_routes:
        raise SystemExit("packaged smoke did not request the rejected updater artifact")

    valid_index = paths.index(valid_routes[0])
    if not any(index < valid_index for index in latest_indices):
        raise SystemExit("valid updater artifact was not requested after valid metadata")

    invalid_index = paths.index(invalid_routes[0])
    if not any(valid_index < index < invalid_index for index in latest_indices):
        raise SystemExit("rejected updater artifact was not requested after invalid metadata")

    if args.state_file:
        expected_routes, pack_routes = _state_routes(args.state_file)
        if set(valid_routes + invalid_routes) - expected_routes:
            raise SystemExit("fixture request log contains an artifact route outside its state")
        if args.require_security:
            _check_security_proofs(args.state_file.parent)
            if args.smoke_state is None:
                raise SystemExit("security verification requires packaged smoke state")
            try:
                smoke = json.loads(args.smoke_state.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SystemExit("packaged smoke state cannot be read") from exc
            phases = {
                row.get("name"): row.get("result")
                for row in smoke.get("phases", [])
                if isinstance(row, dict)
            }
            retention = smoke.get("invalid_retention")
            if phases.get("invalid") != "passed":
                raise SystemExit("packaged smoke did not prove semantic updater rejection")
            if not isinstance(retention, dict) or not all(
                retention.get(key) is True
                for key in ("version_unchanged", "hash_unchanged", "sidecar_healthy")
            ):
                raise SystemExit("packaged smoke did not prove rejection health and retention")
    expected_pack_paths = {
        "valid_manifest": (
            pack_routes["valid_manifest_route"]
            if pack_routes is not None
            else "/findings-pack-manifest.json"
        ),
        "valid_signature": (
            pack_routes["valid_manifest_route"] + ".sig"
            if pack_routes is not None
            else "/findings-pack-manifest.json.sig"
        ),
        "valid_asset": (
            pack_routes["valid_route"] if pack_routes is not None else "/findings-pack.zip"
        ),
        "corrupt_manifest": (
            pack_routes["corrupt_manifest_route"]
            if pack_routes is not None
            else "/findings-pack-corrupt-manifest.json"
        ),
        "corrupt_signature": (
            pack_routes["corrupt_manifest_route"] + ".sig"
            if pack_routes is not None
            else "/findings-pack-corrupt-manifest.json.sig"
        ),
        "corrupt_asset": (
            pack_routes["corrupt_route"]
            if pack_routes is not None
            else "/findings-pack-corrupt.zip"
        ),
    }
    try:
        pack_indices = {
            name: paths.index(path) for name, path in expected_pack_paths.items()
        }
    except ValueError as exc:
        raise SystemExit("packaged smoke did not request every Findings Pack rollback asset") from exc
    pack_order = [
        pack_indices["valid_manifest"],
        pack_indices["valid_signature"],
        pack_indices["valid_asset"],
        pack_indices["corrupt_manifest"],
        pack_indices["corrupt_signature"],
        pack_indices["corrupt_asset"],
    ]
    if pack_order != sorted(pack_order) or len(set(pack_order)) != len(pack_order):
        raise SystemExit("Findings Pack valid and corrupt candidates were not requested in order")

    print(
        f"loopback updater fixture verified "
        f"({len(rows)} requests; valid and rejected updater artifacts; "
        "valid and corrupt Findings Pack candidates; no external endpoint)"
    )


if __name__ == "__main__":
    main()

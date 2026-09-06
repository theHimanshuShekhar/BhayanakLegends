"""Assert the packaged smoke used signed local updater and pack fixtures."""

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


def _state_routes(path: Path) -> set[str]:
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
    return routes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("requests_file", type=Path)
    parser.add_argument("--state-file", type=Path)
    args = parser.parse_args()

    rows = _read_rows(args.requests_file)
    paths = [str(row["path"]) for row in rows]
    latest_indices = [index for index, path in enumerate(paths) if path == "/latest.json"]
    if len(latest_indices) < 2:
        raise SystemExit(
            "packaged smoke must request valid and mismatched updater metadata"
        )
    valid_routes = [path for path in paths if path.startswith("/artifacts/valid/")]
    invalid_routes = [path for path in paths if path.startswith("/artifacts/invalid/")]
    if not valid_routes:
        raise SystemExit("packaged smoke did not download the real valid updater artifact")
    if not invalid_routes:
        raise SystemExit("packaged smoke did not request the rejected updater artifact")
    first_latest, second_latest = latest_indices[0], latest_indices[1]
    if not any(
        first_latest < index < second_latest
        for index, path in enumerate(paths)
        if path in valid_routes
    ):
        raise SystemExit("valid updater artifact was not requested after valid metadata")
    if not any(
        index > second_latest
        for index, path in enumerate(paths)
        if path in invalid_routes
    ):
        raise SystemExit("rejected updater artifact was not requested after invalid metadata")
    pack_manifest = [path for path in paths if path == "/findings-pack-manifest.json"]
    pack_signature = [path for path in paths if path == "/findings-pack-manifest.json.sig"]
    pack_asset = [path for path in paths if path == "/findings-pack.zip"]
    if not pack_manifest or not pack_signature or not pack_asset:
        raise SystemExit(
            "packaged smoke did not activate the signed local Findings Pack fixture"
        )
    if paths.index(pack_signature[0]) < paths.index(pack_manifest[0]):
        raise SystemExit("Findings Pack signature was requested before its manifest")

    if args.state_file:
        expected_routes = _state_routes(args.state_file)
        if set(valid_routes + invalid_routes) - expected_routes:
            raise SystemExit("fixture request log contains an artifact route outside its state")

    print(
        f"loopback updater and Findings Pack fixtures verified "
        f"({len(rows)} requests; valid and rejected artifacts; no external endpoint)"
    )


if __name__ == "__main__":
    main()

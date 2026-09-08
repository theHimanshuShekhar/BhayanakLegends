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
        expected_routes = _state_routes(args.state_file)
        if set(valid_routes + invalid_routes) - expected_routes:
            raise SystemExit("fixture request log contains an artifact route outside its state")

    print(
        f"loopback updater fixture verified "
        f"({len(rows)} requests; valid and rejected artifacts; no external endpoint)"
    )


if __name__ == "__main__":
    main()

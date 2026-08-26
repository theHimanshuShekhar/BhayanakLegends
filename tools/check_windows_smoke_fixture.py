"""Assert the packaged smoke exercised the full loopback updater proof.

The checker requires, at minimum: an updater metadata check, a fetch of the
real valid update artifact, a fetch of the rejected artifact during the
mismatched-signature phase, and the Findings Pack manifest/asset pair. It
rejects any recorded diagnostic that is not a path-only GET row, so a
query-bearing URL, absolute origin, or unexpected host data fails the smoke.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_PATHS = frozenset(
    {
        "/latest.json",
        "/updater/update.bin",
        "/updater/rejected.bin",
        "/findings-pack-manifest.json",
        "/findings-pack.zip",
    }
)
REQUIRED_PATHS = (
    ("/latest.json", "updater metadata check"),
    ("/updater/update.bin", "valid signed updater artifact download"),
    ("/updater/rejected.bin", "rejected-signature artifact download"),
    ("/findings-pack-manifest.json", "Findings Pack manifest check"),
    ("/findings-pack.zip", "Findings Pack asset download"),
)
ROW_KEYS = frozenset({"method", "path"})


def check_requests(rows: list[dict[str, object]]) -> str:
    """Validate the fixture's recorded requests and return a summary line."""

    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            raise SystemExit(
                f"fixture diagnostic row {index} is not path-only method/path data: {row!r}"
            )
        if row["method"] != "GET":
            raise SystemExit(f"unexpected HTTP method in diagnostics: {row['method']!r}")
        path = row["path"]
        if not isinstance(path, str) or not path.startswith("/"):
            raise SystemExit(f"fixture diagnostic is not a bare path: {path!r}")
        for marker in ("?", "#", "@", "://"):
            if marker in path:
                raise SystemExit(
                    f"fixture diagnostic carries query/host data ({marker!r}): {path!r}"
                )

    paths = [row["path"] for row in rows]
    counts = {path: paths.count(path) for path in ALLOWED_PATHS}
    missing = [label for path, label in REQUIRED_PATHS if not counts[path]]
    if missing:
        raise SystemExit("packaged smoke did not prove: " + ", ".join(missing))

    unexpected = sorted({path for path in paths if path not in ALLOWED_PATHS})
    if unexpected:
        raise SystemExit("updater fixture observed unexpected paths: " + ", ".join(unexpected))
    return (
        f"loopback updater proof verified ({len(rows)} requests; "
        f"{counts['/latest.json']} metadata checks, {counts['/updater/update.bin']} valid and "
        f"{counts['/updater/rejected.bin']} rejected artifact downloads; no external endpoint)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("requests_file", type=Path)
    args = parser.parse_args()
    text = args.requests_file.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line]
    print(check_requests(rows))


if __name__ == "__main__":
    main()

"""Assert the packaged smoke only used the loopback updater fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("requests_file", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.requests_file.read_text(encoding="utf-8").splitlines() if line]
    paths = [row.get("path") for row in rows]
    latest = [path for path in paths if path == "/latest.json"]
    if len(latest) < 2:
        raise SystemExit(f"expected two local updater checks, observed {len(latest)}")
    unexpected = sorted({path for path in paths if path not in {"/latest.json", "/artifact.bin"}})
    if unexpected:
        raise SystemExit("updater fixture observed unexpected paths: " + ", ".join(unexpected))
    if "/artifact.bin" not in paths:
        raise SystemExit("invalid-signature phase did not fetch the local artifact")
    print(f"loopback updater fixture verified ({len(rows)} requests; no external endpoint)")


if __name__ == "__main__":
    main()

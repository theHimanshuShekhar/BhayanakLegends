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
    pack_manifest = [path for path in paths if path == "/findings-pack-manifest.json"]
    pack_asset = [path for path in paths if path == "/findings-pack.zip"]
    if not latest:
        raise SystemExit("packaged smoke did not check the local updater fixture")
    allowed = {"/latest.json", "/artifact.bin", "/findings-pack-manifest.json", "/findings-pack.zip"}
    unexpected = sorted({path for path in paths if path not in allowed})
    if unexpected:
        raise SystemExit("updater fixture observed unexpected paths: " + ", ".join(unexpected))
    if not pack_manifest or not pack_asset:
        raise SystemExit("packaged smoke did not activate the local Findings Pack fixture")
    print(
        f"loopback updater and Findings Pack fixtures verified "
        f"({len(rows)} requests; no external endpoint)"
    )


if __name__ == "__main__":
    main()

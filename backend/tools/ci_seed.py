"""Seed a minimal Personal History for CI e2e runs from committed test fixtures."""

import json
import shutil
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "backend" / "tests" / "fixtures"
SEED_DIR = REPO / "data" / "dev-import" / "ci"
SIDECAR = "http://127.0.0.1:23110"
TOKEN = "dev"


def main() -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    puuid = None
    for src in sorted(FIXTURES.glob("SG2_*.json")):
        if src.name.endswith("_timeline.json"):
            continue
        detail = json.loads(src.read_text())
        puuid = puuid or detail["metadata"]["participants"][0]
        shutil.copy(src, SEED_DIR / src.name)
        timeline = src.with_name(src.stem + "_timeline.json")
        if timeline.exists():
            shutil.copy(timeline, SEED_DIR / timeline.name)

    (SEED_DIR / "fetch_state.json").write_text(
        json.dumps({"name": "ci-seed#CI", "puuid": puuid, "status": "complete"})
    )

    req = urllib.request.Request(
        f"{SIDECAR}/dev/import",
        data=json.dumps({"dir": str(SEED_DIR)}).encode(),
        headers={"X-BL-Token": TOKEN, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        print(json.loads(res.read()))


if __name__ == "__main__":
    sys.exit(main())

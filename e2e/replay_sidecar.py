#!/usr/bin/env python3
"""Run the production sidecar with bounded, version-matched replay catalogs.

Only the Data Dragon transport is injected. LCU version discovery, exact live
feature extraction, canonical withholding and synthetic model mechanics still
run through their production paths. No external calls are needed by this replay.
"""
import json
from pathlib import Path

from bhayanak_legends import lcu
from bhayanak_legends.sidecar import main

CATALOG = json.loads((Path(__file__).resolve().parents[1] / "backend/tests/fixtures/lcu/item_catalog.json").read_text())


async def replay_versions():
    return [CATALOG["version"]]


async def replay_items(version):
    if version != CATALOG["version"]:
        raise ValueError("replay has no item evidence for the requested version")
    return {"data": CATALOG["data"]}


if __name__ == "__main__":
    lcu._fetch_versions_default = replay_versions
    lcu._fetch_items_default = replay_items
    main()

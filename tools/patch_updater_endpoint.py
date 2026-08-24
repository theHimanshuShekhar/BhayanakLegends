"""Temporarily point the packaged app updater at a loopback smoke fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    if args.restore:
        if args.backup.exists():
            shutil.copyfile(args.backup, args.config)
        return

    if not args.endpoint or not args.endpoint.startswith("http://127.0.0.1:"):
        raise SystemExit("smoke updater endpoint must remain loopback-only")
    if args.backup.exists():
        raise SystemExit(f"refusing to overwrite existing backup: {args.backup}")

    args.backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.config, args.backup)
    document = json.loads(args.config.read_text(encoding="utf-8"))
    updater = document.setdefault("plugins", {}).setdefault("updater", {})
    if not isinstance(updater.get("endpoints"), list) or not updater["endpoints"]:
        raise SystemExit("tauri updater has no configured endpoint")
    updater["endpoints"] = [args.endpoint]
    args.config.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

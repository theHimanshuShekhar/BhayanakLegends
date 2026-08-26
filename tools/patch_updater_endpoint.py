"""Temporarily point the packaged app updater at a loopback smoke fixture.

The patch replaces the updater endpoints with the loopback fixture URL, swaps
the production public key for the paired job-local smoke public key, and
enables the insecure-transport opt-in that a packaged (release) build requires
to accept an ``http://127.0.0.1`` endpoint. The whole-file backup taken before
patching restores production endpoint, public key, and transport settings on
every exit path via ``--restore``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def restore(backup: Path, config: Path) -> None:
    if backup.exists():
        shutil.copyfile(backup, config)


def load_config(config: Path) -> dict[str, object]:
    try:
        document = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"tauri config is unreadable: {config} ({exc})") from exc
    if not isinstance(document, dict):
        raise SystemExit("tauri config root must be an object")
    return document


def apply_patch(
    config_path: Path,
    *,
    backup: Path,
    endpoint: str,
    pubkey: str,
    set_version: str | None = None,
) -> None:
    if not endpoint.startswith("http://127.0.0.1:"):
        raise SystemExit("smoke updater endpoint must remain loopback-only")
    if not pubkey or not pubkey.strip():
        raise SystemExit("smoke patch requires the paired job-local public key")
    if backup.exists():
        raise SystemExit(f"refusing to overwrite existing backup: {backup}")

    document = load_config(config_path)
    if set_version is not None:
        document["version"] = set_version
    updater = document.setdefault("plugins", {}).setdefault("updater", {})
    if not isinstance(updater.get("endpoints"), list) or not updater["endpoints"]:
        raise SystemExit("tauri updater has no configured endpoint")
    if not updater.get("pubkey"):
        raise SystemExit("tauri updater has no production pubkey to back up")
    updater["endpoints"] = [endpoint]
    updater["pubkey"] = pubkey
    # A packaged (release-mode) binary refuses plain-http endpoints unless this
    # opt-in is present; the backup restores its absence on every exit path.
    updater["dangerousInsecureTransportProtocol"] = True

    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_path, backup)
    config_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--pubkey")
    parser.add_argument("--set-version", dest="set_version")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    if args.restore:
        if args.set_version is not None:
            raise SystemExit("--restore cannot be combined with --set-version")
        if args.backup is None:
            raise SystemExit("--restore requires --backup")
        restore(args.backup, args.config)
        return

    if args.set_version is not None and (args.endpoint or args.pubkey):
        raise SystemExit("--set-version cannot be combined with endpoint patching")
    if bool(args.endpoint) != bool(args.pubkey):
        raise SystemExit("--endpoint and --pubkey must be provided together")
    if not args.endpoint and args.set_version is None:
        raise SystemExit("nothing to do: pass endpoint/pubkey or --set-version")

    if args.endpoint:
        assert args.pubkey is not None
        assert args.backup is not None
        apply_patch(
            args.config,
            backup=args.backup,
            endpoint=args.endpoint,
            pubkey=args.pubkey,
        )
        return

    document = load_config(args.config)
    document["version"] = args.set_version
    args.config.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

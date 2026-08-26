"""Temporarily point the packaged app updater at a loopback smoke fixture.

The patch replaces the updater endpoints with the loopback fixture URL, swaps
the production public key for the paired job-local smoke public key, enables
the insecure-transport opt-in that a packaged (release) build requires for
``http://127.0.0.1``, and bakes smoke-only WebView2 browser arguments into the
window config. The whole-file backup restores every production value on every
exit path via ``--restore``.
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
    browser_args: str,
    set_version: str | None = None,
) -> None:
    if not endpoint.startswith("http://127.0.0.1:"):
        raise SystemExit("smoke updater endpoint must remain loopback-only")
    if not pubkey or not pubkey.strip():
        raise SystemExit("smoke patch requires the paired job-local public key")
    if not browser_args.startswith("--remote-debugging-port="):
        raise SystemExit("smoke browser args must set the remote-debugging port")
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
    app = document.get("app")
    windows = app.get("windows") if isinstance(app, dict) else None
    if not isinstance(windows, list) or not windows or not isinstance(windows[0], dict):
        raise SystemExit("tauri app has no configured window for smoke browser args")
    windows[0]["additionalBrowserArgs"] = browser_args

    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_path, backup)
    config_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--pubkey")
    parser.add_argument("--browser-args")
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

    endpoint_patch_values = (args.endpoint, args.pubkey, args.browser_args)
    if args.set_version is not None and any(endpoint_patch_values):
        raise SystemExit("--set-version cannot be combined with endpoint patching")
    if any(endpoint_patch_values) and not all(endpoint_patch_values):
        raise SystemExit("--endpoint, --pubkey and --browser-args must be provided together")
    if not args.endpoint and args.set_version is None:
        raise SystemExit("nothing to do: pass endpoint/pubkey/browser-args or --set-version")

    if args.endpoint:
        assert args.pubkey is not None
        assert args.browser_args is not None
        assert args.backup is not None
        apply_patch(
            args.config,
            backup=args.backup,
            endpoint=args.endpoint,
            pubkey=args.pubkey,
            browser_args=args.browser_args,
        )
        return

    document = load_config(args.config)
    document["version"] = args.set_version
    args.config.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

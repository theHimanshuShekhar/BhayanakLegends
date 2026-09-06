"""Patch and restore the packaged Tauri updater smoke configuration.

The smoke configuration is deliberately transactional: the first patch keeps a
byte-for-byte backup of the production document, while later ``--reuse-backup``
patches update the loopback endpoint/version without replacing that backup.
Restoration is safe to call from an unconditional workflow cleanup step.
"""

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import shutil
from urllib.parse import urlsplit


_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _loopback_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path
    ):
        raise SystemExit(
            "smoke updater endpoint must be an http URL on literal 127.0.0.1 "
            "without credentials, query, or fragment"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise SystemExit("smoke updater endpoint has an invalid port") from exc
    if port is None or not 1 <= port <= 65535:
        raise SystemExit("smoke updater endpoint must include a valid TCP port")
    return value


def _read_public_key(args: argparse.Namespace) -> str | None:
    if args.public_key and args.public_key_file:
        raise SystemExit("choose --public-key or --public-key-file, not both")
    if args.public_key_file:
        try:
            value = args.public_key_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise SystemExit("smoke updater public key cannot be read") from exc
    else:
        value = (args.public_key or "").strip()
    if args.public_key is not None or args.public_key_file is not None:
        if not value:
            raise SystemExit("smoke updater public key cannot be empty")
        return value
    return None


def _load_document(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"tauri config cannot be read: {path}") from exc
    if not isinstance(document, dict):
        raise SystemExit("tauri config root must be an object")
    plugins = document.get("plugins")
    updater = plugins.get("updater") if isinstance(plugins, dict) else None
    if not isinstance(updater, dict):
        raise SystemExit("tauri updater configuration is missing")
    return document


def _set_browser_args(document: dict[str, object], browser_args: str) -> None:
    if not browser_args.startswith("--remote-debugging-port="):
        raise SystemExit("smoke browser args must set the remote-debugging port")
    app = document.get("app")
    windows = app.get("windows") if isinstance(app, dict) else None
    if not isinstance(windows, list) or not windows or not isinstance(windows[0], dict):
        raise SystemExit("tauri app has no configured window for smoke browser args")
    windows[0]["additionalBrowserArgs"] = browser_args


def _atomic_write(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise SystemExit(f"refusing to replace symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise SystemExit(f"could not write updater configuration: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--public-key")
    parser.add_argument("--public-key-file", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--browser-args")
    parser.add_argument(
        "--allow-insecure-transport",
        action="store_true",
        help="allow HTTP only for the literal loopback endpoint",
    )
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument(
        "--reuse-backup",
        action="store_true",
        help="patch an already-backed-up config without replacing its production backup",
    )
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    if args.config.is_symlink() or args.backup.is_symlink():
        raise SystemExit("updater config and backup must not be symlinks")

    if args.restore:
        if args.backup.exists():
            try:
                backup_bytes = args.backup.read_bytes()
            except OSError as exc:
                raise SystemExit("updater configuration backup cannot be read") from exc
            _atomic_write(args.config, backup_bytes)
            args.backup.unlink(missing_ok=True)
        return

    if not args.endpoint:
        raise SystemExit("--endpoint is required when patching updater configuration")
    endpoint = _loopback_endpoint(args.endpoint)
    if not args.allow_insecure_transport:
        raise SystemExit(
            "HTTP loopback updater patch requires --allow-insecure-transport"
        )
    if args.version is not None and not _VERSION_RE.fullmatch(args.version):
        raise SystemExit("smoke updater version must use semver major.minor.patch")
    public_key = _read_public_key(args)

    if args.backup.exists() and not args.reuse_backup:
        raise SystemExit(f"refusing to overwrite existing backup: {args.backup}")
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    if not args.backup.exists():
        try:
            _atomic_write(args.backup, args.config.read_bytes())
        except OSError as exc:
            raise SystemExit("updater configuration cannot be backed up") from exc

    document = _load_document(args.config)
    if args.browser_args is not None:
        _set_browser_args(document, args.browser_args)
    plugins = document["plugins"]
    assert isinstance(plugins, dict)
    updater = plugins["updater"]
    assert isinstance(updater, dict)
    updater["endpoints"] = [endpoint]
    updater["dangerousInsecureTransportProtocol"] = True
    if public_key is not None:
        updater["pubkey"] = public_key
    if args.version is not None:
        document["version"] = args.version
    _atomic_write(args.config, (json.dumps(document, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()

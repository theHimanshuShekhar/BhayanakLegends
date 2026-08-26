"""Validate the signed Windows updater bundle before release publication.

Tauri's Windows updater metadata contains the URL of the emitted installer and
not a separate signature URL: ``signature`` is the exact text from the detached
``.sig`` file.  This checker keeps that relationship explicit and fails closed
when any part of the inventory is absent or inconsistent.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

WINDOWS_PLATFORM = "windows-x86_64"


class ArtifactCheckError(ValueError):
    """A release updater inventory is incomplete or inconsistent."""


@dataclass(frozen=True)
class ArtifactInventory:
    """The emitted Windows updater files validated by the checker."""

    archive: Path
    signature: Path


def _find_updater_archive(bundle_dir: Path) -> Path:
    if not bundle_dir.is_dir():
        raise ArtifactCheckError("Windows updater bundle directory is missing")

    candidates = sorted(
        path
        for path in bundle_dir.iterdir()
        if path.is_file()
        and (path.name.lower().endswith(".exe") or path.name.lower().endswith(".nsis.zip"))
    )
    if not candidates:
        raise ArtifactCheckError("Windows updater archive is missing")
    if len(candidates) != 1:
        raise ArtifactCheckError("Windows updater archive inventory is ambiguous")
    return candidates[0]


def _load_metadata(metadata_path: Path) -> dict[str, object]:
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactCheckError("latest.json cannot be read as valid JSON") from exc
    if not isinstance(value, dict):
        raise ArtifactCheckError("latest.json root must be an object")
    return value


def _platform_metadata(metadata: dict[str, object]) -> dict[str, object]:
    platforms = metadata.get("platforms")
    if not isinstance(platforms, dict):
        raise ArtifactCheckError("latest.json platforms object is missing")
    platform = platforms.get(WINDOWS_PLATFORM)
    if not isinstance(platform, dict):
        raise ArtifactCheckError(f"latest.json {WINDOWS_PLATFORM} entry is missing")
    return platform


def _metadata_artifact_name(url: object) -> str:
    if not isinstance(url, str) or not url:
        raise ArtifactCheckError(f"latest.json {WINDOWS_PLATFORM} URL is missing")
    path = unquote(urlsplit(url).path)
    name = path.rsplit("/", 1)[-1]
    if not name:
        raise ArtifactCheckError(f"latest.json {WINDOWS_PLATFORM} URL is invalid")
    return name


def check_artifacts(bundle_dir: Path, metadata_path: Path) -> ArtifactInventory:
    """Validate the emitted Windows updater archive against ``latest.json``."""

    archive = _find_updater_archive(Path(bundle_dir))
    signature = archive.with_name(archive.name + ".sig")
    if not signature.is_file():
        raise ArtifactCheckError("Windows updater detached signature is missing")

    try:
        signature_text = signature.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactCheckError("Windows updater detached signature is unreadable") from exc

    platform = _platform_metadata(_load_metadata(Path(metadata_path)))
    if _metadata_artifact_name(platform.get("url")) != archive.name:
        raise ArtifactCheckError(
            f"latest.json {WINDOWS_PLATFORM} URL does not reference the emitted archive"
        )

    metadata_signature = platform.get("signature")
    if not isinstance(metadata_signature, str) or metadata_signature != signature_text:
        raise ArtifactCheckError(
            f"latest.json {WINDOWS_PLATFORM} signature does not match the detached signature"
        )

    return ArtifactInventory(archive=archive, signature=signature)


def _write_latest_json(
    bundle_dir: Path, metadata_path: Path, base_url: str, version: str
) -> None:
    archive = _find_updater_archive(Path(bundle_dir))
    signature = archive.with_name(archive.name + ".sig")
    if not signature.is_file():
        raise ArtifactCheckError("Windows updater detached signature is missing")
    try:
        signature_text = signature.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactCheckError("Windows updater detached signature is unreadable") from exc

    payload = {
        "version": version,
        "platforms": {
            WINDOWS_PLATFORM: {
                "signature": signature_text,
                "url": f"{base_url.rstrip('/')}/{quote(archive.name)}",
            }
        },
    }
    try:
        metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ArtifactCheckError("latest.json cannot be written") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--latest-json", required=True, type=Path)
    parser.add_argument(
        "--write-latest-json",
        action="store_true",
        help="generate the metadata document from the emitted artifact before checking it",
    )
    parser.add_argument("--base-url", help="release download URL prefix for generated metadata")
    parser.add_argument("--version", help="release version for generated metadata")
    args = parser.parse_args(argv)

    if args.write_latest_json and (not args.base_url or not args.version):
        parser.error("--write-latest-json requires --base-url and --version")

    try:
        if args.write_latest_json:
            _write_latest_json(args.bundle_dir, args.latest_json, args.base_url, args.version)
        inventory = check_artifacts(args.bundle_dir, args.latest_json)
    except ArtifactCheckError as exc:
        print(f"Windows updater artifact check failed: {exc}", file=sys.stderr)
        return 1

    print(f"Windows updater artifacts verified: {inventory.archive.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate and package the canonical Findings Pack v2 release payload.

The command consumes the companion pack already present in this repository. It
never derives population values or translates a producer-side export. The ZIP,
manifest, and detached signature input are deterministic; signing is kept in
``sign_findings_pack_manifest.py`` so production credentials never enter this
builder.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from bhayanak_legends.pack import PackError, validate_pack_directory

from findings_pack_payload import (
    archive_pack_directory,
    build_manifest,
    manifest_bytes,
)


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_release(
    pack_dir: Path,
    asset_path: Path,
    manifest_path: Path,
    *,
    download_url: str = "findings-pack.v2.zip",
    min_app_version: str = "0.1.0",
    max_app_version: str | None = None,
) -> dict[str, object]:
    """Validate one pack and write its deterministic asset and manifest."""
    root = Path(pack_dir)
    try:
        validate_pack_directory(root)
    except PackError as exc:
        raise ValueError(f"canonical Findings Pack is invalid: {exc}") from exc
    asset = archive_pack_directory(root)
    manifest = build_manifest(
        root,
        asset,
        download_url=download_url,
        min_app_version=min_app_version,
        max_app_version=max_app_version,
    )
    _atomic_write(Path(asset_path), asset)
    _atomic_write(Path(manifest_path), manifest_bytes(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", type=Path, default=Path("pack"))
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--download-url", default="findings-pack.v2.zip")
    parser.add_argument("--min-app-version", default="0.1.0")
    parser.add_argument("--max-app-version")
    args = parser.parse_args(argv)
    try:
        manifest = build_release(
            args.pack_dir,
            args.asset,
            args.manifest,
            download_url=args.download_url,
            min_app_version=args.min_app_version,
            max_app_version=args.max_app_version,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Findings Pack v2 release payload")
    print(f"  pack_version: {manifest['pack_version']}")
    print(f"  asset: {args.asset}")
    print(f"  manifest: {args.manifest}")
    print(f"  model_artifacts: {len(manifest['required_model_artifacts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

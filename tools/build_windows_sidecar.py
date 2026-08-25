#!/usr/bin/env python3
"""Build and stage the Windows sidecar consumed by the Tauri bundle.

This is the single owner of the PyInstaller recipe used by release and packaged
smoke workflows. Run it from the repository root with the locked backend
environment:

    uv run --project backend --locked python tools/build_windows_sidecar.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SIDECAR_NAME = "bhayanak-legends-sidecar"
TARGET_TRIPLE = "x86_64-pc-windows-msvc"
ENTRYPOINT = Path("backend/src/bhayanak_legends/sidecar.py")
PACK_DIRECTORY = Path("pack")
BACKEND_DIST = Path("backend/dist")
TARGET_DIRECTORY = Path("src-tauri/binaries")


def build_windows_sidecar(
    *,
    repo_root: Path | None = None,
    pyinstaller: str = "pyinstaller",
) -> Path:
    """Build the sidecar and return its staged target-triple executable path."""
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    backend_directory = root / "backend"
    entrypoint = root / ENTRYPOINT
    pack_directory = root / PACK_DIRECTORY
    dist_directory = root / BACKEND_DIST
    source_executable = dist_directory / f"{SIDECAR_NAME}.exe"
    target_executable = (
        root
        / TARGET_DIRECTORY
        / f"{SIDECAR_NAME}-{TARGET_TRIPLE}.exe"
    )

    if not entrypoint.is_file():
        raise FileNotFoundError(f"Sidecar entry point does not exist: {entrypoint}")
    if not pack_directory.is_dir():
        raise FileNotFoundError(f"Findings Pack directory does not exist: {pack_directory}")

    # Never accept an executable left by an earlier invocation. PyInstaller must
    # produce a fresh output before anything is staged into the Tauri bundle.
    source_executable.unlink(missing_ok=True)
    target_executable.unlink(missing_ok=True)

    command = [
        pyinstaller,
        "--onefile",
        "--name",
        SIDECAR_NAME,
        "--add-data",
        f"{pack_directory}{os.pathsep}pack",
        "--collect-submodules",
        "bhayanak_legends",
        str(entrypoint),
    ]
    subprocess.run(command, cwd=backend_directory, check=True)

    if not source_executable.is_file():
        raise RuntimeError(
            f"PyInstaller did not produce the expected executable: {source_executable}"
        )

    target_executable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_executable, target_executable)
    if not target_executable.is_file():
        raise RuntimeError(f"Failed to stage sidecar executable: {target_executable}")
    return target_executable


def main() -> None:
    build_windows_sidecar()


if __name__ == "__main__":
    main()

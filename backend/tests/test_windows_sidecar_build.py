"""Contract tests for the locked Windows sidecar build command."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "build_windows_sidecar.py"
WORKFLOW_FILES = (
    REPO_ROOT / ".github/workflows/release.yml",
    REPO_ROOT / ".github/workflows/windows-smoke.yml",
)


def test_workflows_use_only_the_shared_sidecar_command():
    command = "uv run --project backend --locked python tools/build_windows_sidecar.py"
    for workflow in WORKFLOW_FILES:
        text = workflow.read_text()
        assert text.count(command) == 1
        assert "uv run pyinstaller" not in text
        assert "--add-data" not in text
        assert "--collect-submodules" not in text
        assert "dist/bhayanak-legends-sidecar" not in text



def load_build_tool():
    spec = importlib.util.spec_from_file_location("build_windows_sidecar", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "backend/src/bhayanak_legends").mkdir(parents=True)
    (root / "pack").mkdir()
    (root / "src-tauri/binaries").mkdir(parents=True)
    (root / "backend/src/bhayanak_legends/sidecar.py").write_text("print('sidecar')\n")
    (root / "pack/findings-pack.v1.json").write_text("{}\n")
    return root


def make_fake_pyinstaller(tmp_path: Path) -> Path:
    fake = tmp_path / "pyinstaller"
    fake.write_text(
        """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

capture = os.environ.get('FAKE_PYINSTALLER_ARGS')
if capture:
    pathlib.Path(capture).write_text(json.dumps({'args': sys.argv[1:], 'cwd': str(pathlib.Path.cwd())}))
if os.environ.get('FAKE_PYINSTALLER_WRITE_OUTPUT') == '1':
    output = pathlib.Path.cwd() / 'dist' / 'bhayanak-legends-sidecar.exe'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b'fresh sidecar')
raise SystemExit(int(os.environ.get('FAKE_PYINSTALLER_EXIT', '0')))
"""
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def test_build_copies_target_triple_and_passes_locked_pyinstaller_recipe(tmp_path, monkeypatch):
    tool = load_build_tool()
    root = make_project(tmp_path)
    fake = make_fake_pyinstaller(tmp_path)
    args_file = tmp_path / "args.json"
    monkeypatch.setenv("FAKE_PYINSTALLER_ARGS", str(args_file))
    monkeypatch.setenv("FAKE_PYINSTALLER_WRITE_OUTPUT", "1")
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)

    tool.build_windows_sidecar(repo_root=root, pyinstaller=str(fake))

    target = root / "src-tauri/binaries/bhayanak-legends-sidecar-x86_64-pc-windows-msvc.exe"
    assert target.read_bytes() == b"fresh sidecar"
    invocation = json.loads(args_file.read_text())
    assert invocation["cwd"] == str(root / "backend")
    assert invocation["args"] == [
        "--onefile",
        "--name",
        "bhayanak-legends-sidecar",
        "--add-data",
        f"{root / 'pack'}{os.pathsep}pack",
        "--collect-submodules",
        "bhayanak_legends",
        str(root / "backend/src/bhayanak_legends/sidecar.py"),
    ]


def test_build_rejects_missing_output_and_removes_stale_artifacts(tmp_path, monkeypatch):
    tool = load_build_tool()
    root = make_project(tmp_path)
    fake = make_fake_pyinstaller(tmp_path)
    monkeypatch.setenv("FAKE_PYINSTALLER_WRITE_OUTPUT", "0")
    source = root / "backend/dist/bhayanak-legends-sidecar.exe"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"stale")
    target = root / "src-tauri/binaries/bhayanak-legends-sidecar-x86_64-pc-windows-msvc.exe"
    target.write_bytes(b"stale")

    with pytest.raises(RuntimeError, match="did not produce"):
        tool.build_windows_sidecar(repo_root=root, pyinstaller=str(fake))

    assert not source.exists()
    assert not target.exists()


def test_build_propagates_pyinstaller_failure_without_copying(tmp_path, monkeypatch):
    tool = load_build_tool()
    root = make_project(tmp_path)
    fake = make_fake_pyinstaller(tmp_path)
    monkeypatch.setenv("FAKE_PYINSTALLER_EXIT", "23")
    target = root / "src-tauri/binaries/bhayanak-legends-sidecar-x86_64-pc-windows-msvc.exe"
    target.write_bytes(b"stale")

    with pytest.raises(subprocess.CalledProcessError) as failure:
        tool.build_windows_sidecar(repo_root=root, pyinstaller=str(fake))

    assert failure.value.returncode == 23
    assert not target.exists()

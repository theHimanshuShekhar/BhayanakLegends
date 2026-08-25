from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend" / "tests" / "fixtures"
TOOL = ROOT / "backend" / "tools" / "check_pii.py"
PSEUDONYMIZER = ROOT / "backend" / "tools" / "pseudonymize_fixtures.py"


def load_tool(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_guard_passes_without_output():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--tracked"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_pseudonymization_is_deterministic_and_preserves_projection(tmp_path: Path):
    pseudo = load_tool(PSEUDONYMIZER, "pseudonymizer")
    source = tmp_path / "source"
    fixture_root = source / "backend" / "tests" / "fixtures"
    fixture_root.mkdir(parents=True)
    for name in ("SG2_170114893.json", "SG2_170114893_timeline.json"):
        source_bytes = subprocess.check_output(["git", "show", f"HEAD:backend/tests/fixtures/{name}"])
        (fixture_root / name).write_bytes(source_bytes)

    before = {path.name: path.read_bytes() for path in fixture_root.glob("*.json")}
    replacements = pseudo.build_replacements(fixture_root)
    assert not any(key.startswith("raw-") for key in replacements)
    assert pseudo.pseudonymize_tree(source, replacements) == 2
    once = {path.name: path.read_bytes() for path in fixture_root.glob("*.json")}
    assert pseudo.pseudonymize_tree(source) == 0
    twice = {path.name: path.read_bytes() for path in fixture_root.glob("*.json")}
    assert once == twice

    def projection(value):
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                if key in {"puuid", "summonerId", "riotIdGameName", "riotIdTagline"}:
                    continue
                if key == "participants" and isinstance(child, list) and all(isinstance(item, str) for item in child):
                    continue
                result[key] = projection(child)
            return result
        if isinstance(value, list):
            return [projection(child) for child in value]
        return value

    for name, original in before.items():
        transformed = json.loads(once[name])
        assert projection(json.loads(original)) == projection(transformed)

    detail = json.loads((fixture_root / "SG2_170114893.json").read_text())
    timeline = json.loads((fixture_root / "SG2_170114893_timeline.json").read_text())
    assert set(detail["metadata"]["participants"]) == set(timeline["metadata"]["participants"])
    assert all(value.startswith("fixture-puuid-") for value in detail["metadata"]["participants"])



def test_guard_rejects_injected_identity_without_echoing_value(tmp_path: Path, capsys):
    raw = json.loads(
        subprocess.check_output(["git", "show", "HEAD:backend/tests/fixtures/SG2_170114893.json"])
    )
    guard = load_tool(TOOL, "check_pii")
    raw_value = raw["info"]["participants"][0]["puuid"]
    leak = tmp_path / "leak.json"
    leak.write_text(json.dumps({"puuid": raw_value}), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "leak.json"], check=True)

    assert guard.run(tmp_path, history=False) == 1
    output = capsys.readouterr().out
    assert "leak.json" in output
    assert raw_value not in output
    assert "sha256:" in output
def test_guard_rejects_malformed_synthetic_ordinal(tmp_path: Path):
    guard = load_tool(TOOL, "check_pii_malformed")
    leak = tmp_path / "malformed.json"
    leak.write_text(json.dumps({"puuid": "fixture-puuid-1"}), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "malformed.json"], check=True)
    assert guard.run(tmp_path, history=False) == 1


def test_history_guard_rejects_denylisted_blob(tmp_path: Path, capsys):
    guard = load_tool(TOOL, "check_pii_history")
    raw = json.loads(
        subprocess.check_output(["git", "show", "HEAD:backend/tests/fixtures/SG2_170114893.json"])
    )
    raw_value = raw["info"]["participants"][0]["puuid"]
    leak = tmp_path / "history.json"
    leak.write_text(json.dumps({"puuid": raw_value}), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "history.json"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
        check=True,
    )
    assert guard.run(tmp_path, history=True) == 1
    output = capsys.readouterr().out
    assert raw_value not in output
    assert "history.json@" in output

"""REST contract drift detector: normalized OpenAPI golden + temporary TS parity.

Modes
-----
check   Normalize the live FastAPI OpenAPI document, compare it against the
        reviewed golden artifact, then generate temporary TypeScript from the
        same document and compile bidirectional assignability assertions
        against handwritten ``src/api/types.ts``. Never writes the golden.
update  Refresh the reviewed golden artifact after an intentional, reviewed
        contract change. Does not run the TypeScript parity stage.

Normalization removes descriptions, titles, examples, operation ids, tags,
server/info metadata and key ordering so formatting-only edits never fail the
check while paths, methods, requiredness, nullability, enums and response
schemas still do.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

GOLDEN_PATH = REPO_ROOT / "contracts" / "openapi.golden.json"

# Frozen public REST inventory (docs/CONTRACT.md route table).
INVENTORY: dict[str, set[str]] = {
    "/health": {"GET"},
    "/settings": {"GET", "PUT"},
    "/sync/start": {"POST"},
    "/sync/cancel": {"POST"},
    "/sync/status": {"GET"},
    "/progress/aggregates": {"GET"},
    "/progress/trajectories": {"GET"},
    "/postgame/latest": {"GET"},
    "/benchmarks": {"GET"},
    "/live/status": {"GET"},
    "/live/session": {"GET"},
    "/live/ingame": {"GET"},
    "/history/summary": {"GET"},
    "/pack": {"GET"},
}
EXCLUDED_PATHS = {"/events", "/dev/import"}

STRIP_KEYS = {
    "description",
    "title",
    "example",
    "examples",
    "default",
    "operationId",
    "summary",
    "tags",
    "deprecated",
}

# Generated component schema name -> handwritten export in src/api/types.ts.
TS_PARITY_PAIRS = {
    "Health": "Health",
    "Settings": "Settings",
    "SyncStatus": "SyncStatus",
    "HistorySummary": "HistorySummary",
    "RoleRow": "RoleRow",
    "TrajectoryPoint": "TrajectoryPoint",
    "PatchAggregate": "PatchAggregate",
    "PostGameDigest": "PostGameDigest",
    "AllyCell": "ChampSelectAllyCell",
    "EnemyCell": "ChampSelectEnemyCell",
    "CsBan": "ChampSelectBan",
    "LiveStatus": "LiveStatus",
    "ChampSelectSnapshot": "ChampSelectSnapshot",
    "InGameSnapshot": "InGameSnapshot",
    "PlayerLive": "PlayerLive",
    "ItemLive": "ItemLive",
    "LiveEvent": "LiveEvent",
}


def build_openapi() -> dict[str, Any]:
    """Deterministic app fixture producing the live OpenAPI document."""
    from bhayanak_legends.app import create_app
    from bhayanak_legends.config import SidecarConfig

    with tempfile.TemporaryDirectory(prefix="bl-contract-") as td:
        base = Path(td)
        config = SidecarConfig(
            port=23110,
            token="local-sidecar-development-token-32chars",
            data_dir=base / "data",
            pack_dir=REPO_ROOT / "pack",
        )
        app = create_app(config)
        return app.openapi()


def strip_node(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: strip_node(value)
            for key, value in sorted(node.items())
            if key not in STRIP_KEYS
        }
    if isinstance(node, list):
        return [strip_node(item) for item in node]
    return node


def normalize(doc: dict[str, Any]) -> dict[str, Any]:
    cleaned = strip_node(json.loads(json.dumps(doc)))
    paths = {}
    for path, methods in cleaned.get("paths", {}).items():
        if path not in INVENTORY:
            continue
        kept = {
            method.upper(): ops
            for method, ops in methods.items()
            if method.upper() in {"GET", "PUT", "POST"}
        }
        if kept:
            paths[path] = kept
    return {"paths": paths, "components": cleaned.get("components", {})}


def first_drift(live: Any, golden: Any, prefix: str = "") -> str | None:
    if type(live) is not type(golden):
        return prefix or "<root>"
    if isinstance(live, dict):
        for key in sorted(set(live) | set(golden)):
            if key not in live or key not in golden:
                return f"{prefix}/{key}"
            drift = first_drift(live[key], golden[key], f"{prefix}/{key}")
            if drift:
                return drift
        return None
    if isinstance(live, list):
        if len(live) != len(golden):
            return f"{prefix}[]"
        for index, (a, b) in enumerate(zip(live, golden)):
            drift = first_drift(a, b, f"{prefix}[{index}]")
            if drift:
                return drift
        return None
    return None if live == golden else prefix


def verify_inventory(normalized: dict) -> list[str]:
    problems: list[str] = []
    paths = normalized["paths"]
    for path, methods in INVENTORY.items():
        if path not in paths:
            problems.append(f"missing documented path {path}")
            continue
        missing = methods - set(paths[path])
        if missing:
            problems.append(f"{path} missing methods {sorted(missing)}")
    for excluded in EXCLUDED_PATHS:
        if excluded in paths:
            problems.append(f"excluded path leaked into contract: {excluded}")
    return problems


def ts_type_for(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        parts = [ts_type_for(part) for part in schema["anyOf"]]
        return " | ".join(parts)
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    kind = schema.get("type")
    if kind == "null":
        return "null"
    if kind == "string":
        return "string"
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "array":
        items = schema.get("items") or {}
        return f"Array<{ts_type_for(items)}>"
    return "unknown"


def render_interface(name: str, schema: dict[str, Any]) -> str:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop_name, prop_schema in properties.items():
        optional = ""  # response_model serializes every field; treat as required
        lines.append(f"  {prop_name}{optional}: {ts_type_for(prop_schema)};")
    lines.append("}")
    return "\n".join(lines)


def generate_typescript(doc: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    components = doc.get("components", {}).get("schemas", {})
    for name, schema in components.items():
        if not (schema.get("type") == "object" or "properties" in schema):
            continue
        body = render_interface(name, schema)
        refs = sorted({m for m in re.findall(r"\b[A-Z][A-Za-z0-9]*\b", body) if m in components and m != name})
        if refs:
            imports = "\n".join(f"import type {{ {ref} }} from './{ref}';" for ref in refs)
            body = imports + "\n\n" + body
        (out_dir / f"{name}.ts").write_text(body + "\n")


def render_assertions(pairs: dict[str, str]) -> str:
    lines: list[str] = ["// AUTO-GENERATED inside a temporary directory; safe to delete."]
    for generated, handwritten in sorted(pairs.items()):
        lines.append(
            f'import type {{ {handwritten} as HW_{handwritten} }} from "../src/api/types";'
        )
        lines.append(f"import type {{ {generated} as G_{generated} }} from './generated/{generated}';")
    for generated, handwritten in sorted(pairs.items()):
        lines.append(
            f"type _gen2hw_{generated} = G_{generated} extends HW_{handwritten} ? true : never;"
        )
        lines.append(
            f"type _hw2gen_{generated} = HW_{handwritten} extends G_{generated} ? true : never;"
        )
        lines.append(f"const _ok_gen2hw_{generated}: _gen2hw_{generated} = true;")
        lines.append(f"const _ok_hw2gen_{generated}: _hw2gen_{generated} = true;")
    return "\n".join(lines) + "\n"


def run_ts_parity(doc: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    components = doc.get("components", {}).get("schemas", {})
    handwritten_src = (REPO_ROOT / "src" / "api" / "types.ts").read_text()
    exported = set(re.findall(r"export (?:interface|type) (\w+)", handwritten_src))
    active_pairs: dict[str, str] = {}
    for generated, handwritten in TS_PARITY_PAIRS.items():
        if generated not in components:
            failures.append(f"generated schema absent for {generated}")
        elif handwritten not in exported:
            failures.append(f"handwritten type absent for {handwritten}")
        else:
            active_pairs[generated] = handwritten
    if failures:
        return failures

    tmp_root = Path(tempfile.mkdtemp(prefix=".contract-tmp-", dir=REPO_ROOT))
    try:
        gen_dir = tmp_root / "generated"
        generate_typescript(doc, gen_dir)
        (tmp_root / "assertions.ts").write_text(render_assertions(active_pairs))
        completed = subprocess.run(
            [
                "pnpm", "exec", "tsc", "--noEmit", "--strict", "--skipLibCheck",
                "--target", "es2020", "--module", "esnext",
                "--moduleResolution", "bundler",
                str(tmp_root / "assertions.ts"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            output = (completed.stdout + completed.stderr).strip().splitlines()
            assertion_lines = (tmp_root / "assertions.ts").read_text().splitlines()
            named: list[str] = []
            for line in output:
                match = re.search(r"assertions\.ts\((\d+),", line)
                if match:
                    lineno = int(match.group(1)) - 1
                    source = assertion_lines[lineno] if lineno < len(assertion_lines) else ""
                    name_match = re.search(r"_ok_(gen2hw|hw2gen)_(\w+)", source)
                    if name_match:
                        direction, name = name_match.groups()
                        named.append(
                            f"{name}: {'generated -> handwritten' if direction == 'gen2hw' else 'handwritten -> generated'} not assignable"
                        )
                        continue
                named.append(line)
            seen: set[str] = set()
            unique = [item for item in named if not (item in seen or seen.add(item))]
            failures.append("TypeScript mutual assignability failed:\n" + "\n".join(unique[:12]))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["check", "update"])
    args = parser.parse_args()

    doc = normalize(build_openapi())
    problems = verify_inventory(doc)

    if args.mode == "update":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        print(f"golden updated: {GOLDEN_PATH}")
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0

    if not GOLDEN_PATH.exists():
        print(f"golden missing: {GOLDEN_PATH}", file=sys.stderr)
        return 1
    golden = json.loads(GOLDEN_PATH.read_text())
    drift = first_drift(doc, golden)
    if drift:
        print(f"OpenAPI drift at {drift}", file=sys.stderr)
        return 1
    failures = run_ts_parity(doc)
    failures.extend(problems)
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

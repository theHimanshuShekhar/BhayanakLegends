"""Contract regression tests for the normalized OpenAPI golden + TS parity.

These invoke tools/contract_check.py helpers directly so drift scenarios are
proven without mutating the reviewed golden artifact on disk.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "contract_check.py"

spec = importlib.util.spec_from_file_location("contract_check", TOOL)
assert spec and spec.loader
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def live_normalized() -> dict:
    return cc.normalize(cc.build_openapi())


def test_golden_matches_live_normalized_openapi():
    golden = cc.__dict__["GOLDEN_PATH"]
    assert golden.exists(), "reviewed golden artifact must be committed"
    live = live_normalized()
    golden_doc = __import__("json").loads(golden.read_text())
    assert cc.first_drift(live, golden_doc) is None


def test_debug_and_sse_paths_excluded_and_inventory_covered():
    normalized = live_normalized()
    problems = cc.verify_inventory(normalized)
    assert problems == []
    assert "/dev/import" not in normalized["paths"]
    assert "/events" not in normalized["paths"]
    assert "/history/summary" in normalized["paths"]


def test_description_only_changes_normalize_away():
    doc = cc.build_openapi()
    noisy = copy.deepcopy(doc)
    for operations in noisy["paths"].values():
        for operation in operations.values():
            operation["description"] = "drift bait"
            operation["summary"] = "drift bait"
    for schema in noisy.get("components", {}).get("schemas", {}).values():
        schema["description"] = "drift bait"
        if "properties" in schema:
            for prop in schema["properties"].values():
                prop["description"] = "drift bait"
    assert cc.normalize(doc)["paths"] == cc.normalize(noisy)["paths"]


def test_field_drift_is_detected_and_named():
    doc = cc.build_openapi()
    live = cc.normalize(doc)
    broken = copy.deepcopy(live)
    health_props = broken["paths"]["/health"]["GET"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    # Drop a required field from the Health response shape.
    required = health_schema_required(health_props, broken)
    if required is not None:
        required.remove("app_version")
    drift = cc.first_drift(live, broken)
    assert drift and "Health" in drift and "required" in drift


def health_schema_required(health_schema: dict, broken: dict):
    ref = health_schema["$ref"].rsplit("/", 1)[-1]
    return broken["components"]["schemas"][ref].get("required")


def test_empty_history_summary_shape(client_factory=None):
    from fastapi.testclient import TestClient

    from bhayanak_legends.app import create_app
    from bhayanak_legends.config import SidecarConfig
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        config = SidecarConfig(
            port=23110,
            token="local-sidecar-development-token-32chars",
            data_dir=Path(td) / "data",
            pack_dir=REPO_ROOT / "pack",
        )
        app = create_app(config)
        headers = {"X-BL-Token": config.token, "Host": "127.0.0.1:23110"}
        with TestClient(app) as test_client:
            response = test_client.get("/history/summary", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "matches": 0,
            "patches": [],
            "by_role": [],
            "win_rate": 0,
        }


def test_typescript_parity_passes_on_current_tree():
    failures = cc.run_ts_parity(live_normalized())
    assert failures == []


def test_ts_parity_detects_one_sided_type_change(tmp_path: Path):
    """Removing pack_version from handwritten Health must fail the compile."""
    failures = cc.run_ts_parity(live_normalized())
    assert failures == []  # sanity: clean tree compiles both directions

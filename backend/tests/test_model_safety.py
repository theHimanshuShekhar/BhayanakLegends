"""Focused model-card, ONNX, and pack activation safety tests."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import shutil
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bhayanak_legends.inference import InferenceRuntime
from bhayanak_legends.pack import PackError, PackStore, validate_pack_directory
from bhayanak_legends.pack_v2 import PackV2ModelCard
from pack_fixture_helpers import (
    canonical_model_assets,
    declared_model_assets,
    minimal_pack,
    model_manifest_pins,
    write_assets,
)
from bhayanak_legends.release_channel import ReleaseChannel

ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = ROOT / "pack"
SCHEMA_PATH = PACK_DIR / "pack.schema.json"

def _onnx_bytes(*, output: str = "probability", operator: str = "Identity") -> bytes:
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper

    input_info = helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, 1])
    output_info = helper.make_tensor_value_info("probability", TensorProto.FLOAT, [None, 1])
    node = helper.make_node(operator, ["features"], [output], name="fixture-node")
    graph = helper.make_graph([node], "fixture", [input_info], [output_info])
    model = helper.make_model(
        graph,
        producer_name="bhayanak-model-safety-test",
        opset_imports=[helper.make_operatorsetid("", 13)],
    )
    return model.SerializeToString()


def _constant_onnx_bytes(value: float) -> bytes:
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper

    tensor = helper.make_tensor("constant", TensorProto.FLOAT, [1, 1], [value])
    output_info = helper.make_tensor_value_info("probability", TensorProto.FLOAT, [None, 1])
    node = helper.make_node("Constant", [], ["probability"], value=tensor)
    graph = helper.make_graph([node], "fixture", [], [output_info])
    model = helper.make_model(
        graph,
        producer_name="bhayanak-model-safety-test",
        opset_imports=[helper.make_operatorsetid("", 13)],
    )
    return model.SerializeToString()


def _card() -> dict:
    return {
        "model_id": "personal-what-if",
        "model_version": "fixture-1",
        "feature_contract_version": "fixture-contract",
        "input_names": ["features"],
        "output_names": ["probability"],
        "features": [
            {
                "name": "x",
                "dtype": "float32",
                "unit": "probability",
                "source": "deterministic fixture",
                "adjustable": True,
                "bounds": {"min": 0.0, "max": 1.0},
            }
        ],
        "feature_order": ["x"],
        "preprocessing": [
            {"name": "identity-x", "feature": "x", "operation": "identity"}
        ],
        "bounds": {"x": {"min": 0.0, "max": 1.0}},
        "patch_scope": {"min": "14.17", "max": "16.17"},
        "validation": {
            "grouped_holdout": {"auc": 1.0},
            "temporal_holdout": {"auc": 1.0},
            "calibration": {"ece": 0.0},
            "parity": {"fixture": True},
            "gates": {"grouped": True, "temporal": True, "parity": True},
        },
        "caveats": ["Deterministic test fixture only."],
        "smoke_test": {"features": [0.25], "expected": 0.25, "tolerance": 1e-6},
    }


def _fixture_pack(tmp_path: Path, *, artifact: bytes | None = None) -> tuple[Path, dict, bytes, dict]:
    artifact = artifact or _onnx_bytes()
    pack = minimal_pack()
    canonical_assets = canonical_model_assets(
        pack,
        exclude_model_keys={"personal_what_if"},
    )
    raw_card = _card()

    card = PackV2ModelCard.model_validate(raw_card).model_dump(mode="json")
    card_bytes = json.dumps(card, separators=(",", ":"), ensure_ascii=False).encode()
    pack["feature_contracts"]["models"]["personal_what_if"] = "fixture-contract"
    pack["models"]["personal_what_if"] = {
        "model_id": "personal-what-if",
        "release_status": "available",
        "artifact": {
            "path": "models/fixture.onnx",
            "format": "onnx",
            "sha256": hashlib.sha256(artifact).hexdigest(),
            "size": len(artifact),
            "model_card_path": "models/fixture.card.json",
            "model_card_sha256": hashlib.sha256(card_bytes).hexdigest(),
            "model_card_size": len(card_bytes),
        },
        "model_card": card,
    }
    root = tmp_path / "active"
    (root / "models").mkdir(parents=True)
    (root / "findings-pack.v2.json").write_text(
        json.dumps(pack, separators=(",", ":")), encoding="utf-8"
    )
    shutil.copy2(SCHEMA_PATH, root / "pack.schema.json")
    write_assets(root, canonical_assets)
    write_assets(
        root,
        {
            "models/fixture.onnx": artifact,
            "models/fixture.card.json": card_bytes,
        },
    )
    return root, pack, artifact, card


def test_deterministic_onnx_fixture_validates_and_survives_restart(tmp_path: Path) -> None:
    root, _pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    validate_pack_directory(root)
    store = PackStore(root)
    runtime = InferenceRuntime(store)
    result = runtime.predict("personal_what_if", {"x": 0.25}, patch="16.17")
    assert result.status == "available"
    assert result.probability == pytest.approx(0.25, abs=1e-6)

    restarted = PackStore(root)
    restarted.initialize()
    after_restart = InferenceRuntime(restarted).predict(
        "personal_what_if", {"x": 0.25}, patch="16.17"
    )
    assert after_restart.status == "available"
    assert after_restart.probability == pytest.approx(0.25, abs=1e-6)


def test_runtime_requires_exact_features_and_declared_domain(tmp_path: Path) -> None:
    root, _pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    runtime = InferenceRuntime(PackStore(root))
    assert runtime.predict("personal_what_if", {"x": 0.25, "extra": 1}).status == "suppressed"
    assert runtime.predict("personal_what_if", {}).status == "suppressed"
    out_of_domain = runtime.predict("personal_what_if", {"x": 1.1})
    assert out_of_domain.status == "out-of-domain"
    assert "fixture.onnx" not in (out_of_domain.reason or "")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_artifact", "missing"),
        ("artifact_hash", "hash mismatch"),
        ("card_hash", "hash mismatch"),
        ("card_content", "model card"),
        ("extra_artifact", "undeclared"),
        ("bad_onnx", "runtime validation"),
        ("smoke", "runtime validation"),
    ],
)
def test_bounded_model_failures_are_rejected_before_activation(
    tmp_path: Path, mutation: str, message: str
) -> None:
    root, pack, artifact, card_payload = _fixture_pack(tmp_path)
    model_artifact = pack["models"]["personal_what_if"]["artifact"]
    artifact_path = root / model_artifact["path"]
    card_path = root / model_artifact["model_card_path"]
    if mutation == "missing_artifact":
        artifact_path.unlink()
    elif mutation == "artifact_hash":
        model_artifact["sha256"] = hashlib.sha256(b"different").hexdigest()
        (root / "findings-pack.v2.json").write_text(json.dumps(pack), encoding="utf-8")
    elif mutation == "card_hash":
        model_artifact["model_card_sha256"] = hashlib.sha256(b"different").hexdigest()
        (root / "findings-pack.v2.json").write_text(json.dumps(pack), encoding="utf-8")
    elif mutation == "card_content":
        card_path.write_text(json.dumps({**card_payload, "model_version": "tampered"}), encoding="utf-8")
    elif mutation == "extra_artifact":
        (root / "models" / "extra.onnx").write_bytes(b"not declared")
    elif mutation == "bad_onnx":
        artifact_path.write_bytes(b"not an onnx model")
        model_artifact["sha256"] = hashlib.sha256(b"not an onnx model").hexdigest()
        model_artifact["size"] = len(b"not an onnx model")
        (root / "findings-pack.v2.json").write_text(json.dumps(pack), encoding="utf-8")
    elif mutation == "smoke":
        bad = _constant_onnx_bytes(0.9)
        artifact_path.write_bytes(bad)
        model_artifact["sha256"] = hashlib.sha256(bad).hexdigest()
        model_artifact["size"] = len(bad)
        (root / "findings-pack.v2.json").write_text(json.dumps(pack), encoding="utf-8")
    with pytest.raises(PackError, match=message):
        validate_pack_directory(root)


def test_available_surrender_advisor_is_rejected_by_pack_contract(tmp_path: Path) -> None:
    root, pack, _artifact, card = _fixture_pack(tmp_path)
    surrender = copy.deepcopy(pack["models"]["personal_what_if"])
    surrender["model_id"] = "surrender-advisor"
    surrender["model_card"]["model_id"] = "surrender-advisor"
    pack["feature_contracts"]["models"]["surrender_advisor"] = "fixture-contract"
    pack["models"]["surrender_advisor"] = surrender
    (root / "findings-pack.v2.json").write_text(json.dumps(pack), encoding="utf-8")
    with pytest.raises(PackError, match="Surrender Advisor"):
        validate_pack_directory(root)


@pytest.mark.asyncio
async def test_release_manifest_pins_available_model_card_and_artifact(tmp_path: Path) -> None:
    root, pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    release_pack = copy.deepcopy(pack)
    release_pack["pack_version"] = "v3"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("findings-pack.v2.json", json.dumps(release_pack))
        archive.writestr("pack.schema.json", SCHEMA_PATH.read_bytes())
        for relative, data in declared_model_assets(pack, root).items():
            archive.writestr(relative, data)
    asset = output.getvalue()
    contracts = release_pack["feature_contracts"]
    manifest = {
        "pack_version": "v3",
        "schema_version": 2,
        "feature_contract_versions": {
            "population": contracts["population"],
            **contracts["models"],
        },
        "download_url": "asset.zip",
        "sha256": hashlib.sha256(asset).hexdigest(),
        "size": len(asset),
        "required_model_artifacts": model_manifest_pins(release_pack),
    }
    private_key = Ed25519PrivateKey.generate()
    raw_manifest = json.dumps(manifest).encode()
    signature = private_key.sign(raw_manifest)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/manifest.json":
            return httpx.Response(200, content=raw_manifest, request=request)
        if request.url.path == "/manifest.json.sig":
            return httpx.Response(200, content=signature, request=request)
        if request.url.path == "/asset.zip":
            return httpx.Response(200, content=asset, request=request)
        return httpx.Response(404, request=request)

    store = PackStore(root)
    store.initialize()
    assert store.version() == "v2"

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = ReleaseChannel(
        root,
        manifest_url="http://127.0.0.1:8080/manifest.json",
        app_version="0.1.0",
        client=client,
        allow_loopback_http=True,
        manifest_public_key=private_key.public_key().public_bytes_raw(),
        pack_store=store,
    )
    result = await channel.check_and_activate("v2")
    assert result.activated
    assert store.version() == "v3"
    active = channel.pack_dir
    assert active != root
    assert json.loads((root / "findings-pack.v2.json").read_text())["pack_version"] == "v2"
    assert json.loads((active / "findings-pack.v2.json").read_text())["pack_version"] == "v3"
    for relative, data in declared_model_assets(release_pack, root).items():
        assert (active / relative).read_bytes() == data

    await client.aclose()


def test_corrupt_active_model_recovers_last_known_good_pack(tmp_path: Path) -> None:
    root, _pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    store = PackStore(root)
    store.initialize()
    assert store.load()["pack_version"] == "v2"
    (root / "models" / "fixture.onnx").unlink()

    restarted = PackStore(root)
    restarted.initialize()
    assert (root / "models" / "fixture.onnx").is_file()
    assert InferenceRuntime(restarted).predict(
        "personal_what_if", {"x": 0.25}
    ).status == "available"


def test_restart_does_not_promote_orphan_generation_without_committed_pointer(
    tmp_path: Path,
) -> None:
    root, pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    orphan = root.parent / ".active-generation-orphan"
    shutil.copytree(root, orphan)
    orphan_pack = {**pack, "pack_version": "v9"}
    (orphan / "findings-pack.v2.json").write_text(
        json.dumps(orphan_pack),
        encoding="utf-8",
    )

    restarted = PackStore(root)
    restarted.initialize()

    assert restarted.version() == "v2"
    assert restarted.pack_dir == root
    assert not orphan.exists()


def test_committed_generation_survives_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    store = PackStore(root)
    store.initialize()
    candidate = tmp_path / "candidate"
    shutil.copytree(root, candidate)
    (candidate / "findings-pack.v2.json").write_text(
        json.dumps({**pack, "pack_version": "v3"}),
        encoding="utf-8",
    )
    transaction = store.activate_candidate(candidate)

    def fail_cleanup(*, keep: Path | None = None) -> None:
        del keep
        raise OSError("simulated Windows handle retention")

    monkeypatch.setattr(store, "_cleanup_generations", fail_cleanup)
    transaction.finalize()
    store.reload()

    assert store.version() == "v3"


def test_failed_pointer_rollback_keeps_cache_on_committed_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    store = PackStore(root)
    store.initialize()
    assert store.version() == "v2"
    candidate = tmp_path / "candidate"
    shutil.copytree(root, candidate)
    (candidate / "findings-pack.v2.json").write_text(
        json.dumps({**pack, "pack_version": "v3"}),
        encoding="utf-8",
    )
    transaction = store.activate_candidate(candidate)

    def fail_pointer_removal() -> None:
        raise OSError("simulated pointer rollback failure")

    monkeypatch.setattr(store, "_remove_pointer", fail_pointer_removal)
    with pytest.raises(OSError, match="pointer rollback"):
        transaction.rollback()

    assert store.version() == "v3"


def test_activation_waits_for_outer_what_if_read_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    store = PackStore(root)
    store.initialize()
    runtime = InferenceRuntime(store)

    candidate = tmp_path / "candidate"
    shutil.copytree(root, candidate)
    candidate_pack = json.loads((candidate / "findings-pack.v2.json").read_text())
    candidate_pack["pack_version"] = "v3"
    (candidate / "findings-pack.v2.json").write_text(
        json.dumps(candidate_pack),
        encoding="utf-8",
    )

    first_prediction = threading.Event()
    allow_second_prediction = threading.Event()
    second_prediction = threading.Event()
    activation_started = threading.Event()
    activation_done = threading.Event()
    calls = 0
    original_predict = runtime._predict_unlocked

    def coordinated_predict(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_prediction.set()
            if not allow_second_prediction.wait(timeout=2):
                raise RuntimeError("second prediction was not released")
        elif calls == 2:
            second_prediction.set()
        return original_predict(*args, **kwargs)

    monkeypatch.setattr(runtime, "_predict_unlocked", coordinated_predict)
    results = []

    def run_what_if() -> None:
        results.append(
            runtime.what_if(
                {"x": 0.5},
                {"x": 0.25},
                patch="16.17",
            )
        )

    def activate() -> None:
        activation_started.set()
        transaction = store.activate_candidate(candidate)
        transaction.finalize()
        activation_done.set()

    inference_thread = threading.Thread(target=run_what_if)
    activation_thread = threading.Thread(target=activate)
    inference_thread.start()
    assert first_prediction.wait(timeout=2)
    activation_thread.start()
    assert activation_started.wait(timeout=2)
    assert not activation_done.wait(timeout=0.05)
    allow_second_prediction.set()
    assert second_prediction.wait(timeout=2)
    assert not activation_done.is_set()
    inference_thread.join(timeout=2)
    activation_thread.join(timeout=2)

    assert not inference_thread.is_alive()
    assert not activation_thread.is_alive()
    assert results and results[0].status == "available"
    assert activation_done.is_set()

def test_surrender_runtime_gate_runs_before_session_loading(tmp_path: Path, monkeypatch) -> None:
    root, _pack, _artifact, _card_payload = _fixture_pack(tmp_path)
    runtime = InferenceRuntime(PackStore(root))
    malformed_pack = SimpleNamespace(
        pack_version="v2",
        models={
            "surrender_advisor": SimpleNamespace(
                model_id="surrender-advisor",
                release_status="available",
                artifact=object(),
                model_card=object(),
            )
        },
    )
    monkeypatch.setattr(runtime, "_pack_v2", lambda: (malformed_pack, None))
    monkeypatch.setattr(runtime, "_session", lambda *_args: pytest.fail("must not load session"))
    result = runtime.predict("surrender_advisor", {"x": 0.25})
    assert result.status == "suppressed"
    assert result.reason == "Surrender Advisor is unavailable"

#!/usr/bin/env python3
"""Exercise canonical Findings Pack activation and corrupt-candidate recovery.

This smoke helper intentionally uses a fresh PackStore with no active pack. The
first signed candidate is the exact canonical v4 payload served by the Windows
fixture, so its pack identity is not fabricated or rewritten. A second signed
manifest is manifest-only and declares the smoke-only newer version
``v5-smoke-invalid-129`` while pointing to a ZIP whose Findings Pack JSON is
unloadable. Both candidates travel through the real ReleaseChannel validation
and PackStore activation path; the corrupt follow-up receives the retained
active version exactly as production startup does. Separate verifier
subprocesses reconstruct PackStore after the valid and rejected candidates,
proving the selected generation, canonical bytes, and every available model's
card smoke proof survive process boundaries.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from bhayanak_legends.inference import InferenceRuntime
from bhayanak_legends.pack import PackStore
from bhayanak_legends.release_channel import ReleaseChannel
from findings_pack_payload import archive_pack_directory


def _public_key(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("manifest public key is not valid base64") from exc
    if len(decoded) != 32:
        raise ValueError("manifest public key must decode to 32 bytes")
    return decoded


async def _run_candidate(
    store: PackStore,
    manifest_url: str,
    manifest_public_key: bytes,
    current_version: str | None,
) -> tuple[bool, str | None]:
    channel = ReleaseChannel(
        store.pack_dir,
        manifest_url=manifest_url,
        app_version="1.0.0",
        allow_loopback_http=True,
        manifest_public_key=manifest_public_key,
        pack_store=store,
    )
    result = await channel.check_and_activate(current_version)
    return result.activated, result.reason


def _card_smoke(
    model_key: str,
    declaration: dict[str, object],
) -> tuple[dict[str, float], str, float, float]:
    card = declaration.get("model_card")
    if not isinstance(card, dict):
        raise RuntimeError(f"available {model_key} model card is missing")
    order = card.get("feature_order")
    smoke = card.get("smoke_test")
    patch_scope = card.get("patch_scope")
    if (
        not isinstance(order, list)
        or not order
        or any(not isinstance(name, str) for name in order)
        or not isinstance(smoke, dict)
        or not isinstance(smoke.get("features"), list)
        or len(order) != len(smoke["features"])
        or not isinstance(patch_scope, dict)
        or not isinstance(patch_scope.get("max"), str)
    ):
        raise RuntimeError(f"available {model_key} model smoke contract is malformed")
    try:
        baseline = dict(zip(order, (float(value) for value in smoke["features"]), strict=True))
        expected = float(smoke["expected"])
        tolerance = float(smoke["tolerance"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"available {model_key} model smoke values are malformed") from exc
    if tolerance < 0:
        raise RuntimeError(f"available {model_key} model smoke tolerance is invalid")
    return baseline, patch_scope["max"], expected, tolerance


def _model_proof(store: PackStore) -> dict[str, object]:
    pack = store.load()
    models = pack.get("models")
    if not isinstance(models, dict):
        raise RuntimeError("canonical Findings Pack model inventory is malformed")
    runtime = InferenceRuntime(store)
    available = {
        key: declaration
        for key, declaration in models.items()
        if isinstance(declaration, dict) and declaration.get("release_status") == "available"
    }
    if not available:
        raise RuntimeError("canonical Findings Pack has no available models")
    results: dict[str, dict[str, object]] = {}
    baselines: dict[str, tuple[dict[str, float], str, float, float]] = {}
    for model_key, declaration in available.items():
        baseline, patch, expected, tolerance = _card_smoke(model_key, declaration)
        baselines[model_key] = (baseline, patch, expected, tolerance)
        prediction = runtime.predict(model_key, baseline, patch=patch)
        if (
            prediction.status != "available"
            or prediction.probability is None
            or abs(prediction.probability - expected) > tolerance
            or prediction.pack_version != pack["pack_version"]
        ):
            raise RuntimeError(
                f"canonical {model_key} model smoke failed: "
                f"status={prediction.status!r}, probability={prediction.probability!r}, "
                f"expected={expected!r}, tolerance={tolerance!r}"
            )
        results[model_key] = {
            "model_version": prediction.model_version,
            "probability": prediction.probability,
            "expected": expected,
            "tolerance": tolerance,
            "status": prediction.status,
        }

    personal = results.get("personal_what_if")
    if personal is not None:
        baseline, patch, expected, tolerance = baselines["personal_what_if"]
        what_if = runtime.what_if({}, baseline, patch=patch)
        if (
            what_if.status != "available"
            or what_if.probability is None
            or what_if.baseline_probability is None
            or abs(what_if.probability - expected) > tolerance
            or abs(what_if.baseline_probability - expected) > tolerance
            or what_if.pack_version != pack["pack_version"]
        ):
            raise RuntimeError("canonical Personal What-If request failed its model-card smoke contract")
        personal["what_if_status"] = what_if.status
        personal["what_if_probability"] = what_if.probability
        personal["what_if_baseline_probability"] = what_if.baseline_probability
    return {"available_model_keys": sorted(available), "models": results}


def _state(store: PackStore) -> tuple[str, str, str]:
    pointer = store.storage_parent / ".active-pointer"
    generation = pointer.read_text(encoding="ascii").strip()
    active_archive = archive_pack_directory(store.pack_dir)
    pack = store.load()
    return generation, str(pack["pack_version"]), hashlib.sha256(active_archive).hexdigest()




def verify_store(
    root: Path,
    *,
    expected_generation: str,
    expected_version: str,
    expected_hash: str,
) -> dict[str, object]:
    store = PackStore(Path(root) / "active")
    store.initialize()
    generation, version, archive_hash = _state(store)
    if generation != expected_generation:
        raise RuntimeError("Findings Pack generation changed across process restart")
    if version != expected_version:
        raise RuntimeError("Findings Pack version changed across process restart")
    if archive_hash != expected_hash:
        raise RuntimeError("Findings Pack bytes changed across process restart")
    return {
        "generation": generation,
        "pack_version": version,
        "archive_sha256": archive_hash,
        "model": _model_proof(store),
    }


def _verify_in_subprocess(
    root: Path,
    *,
    expected_generation: str,
    expected_version: str,
    expected_hash: str,
) -> dict[str, object]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "verify",
        "--root",
        str(root),
        "--expected-generation",
        expected_generation,
        "--expected-version",
        expected_version,
        "--expected-hash",
        expected_hash,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "verifier failed"
        raise RuntimeError(f"Findings Pack restart verifier failed: {detail}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Findings Pack restart verifier returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Findings Pack restart verifier returned an invalid object")
    return value


def run(
    pack_dir: Path,
    root: Path,
    valid_manifest_url: str,
    corrupt_manifest_url: str,
    manifest_public_key: str,
) -> dict[str, object]:
    pack_dir = Path(pack_dir).resolve()
    root = Path(root).resolve()
    if root.exists():
        raise RuntimeError(f"isolated PackStore root must not already exist: {root}")
    root.mkdir(parents=True)
    canonical = json.loads((pack_dir / "findings-pack.v2.json").read_text(encoding="utf-8"))
    expected_version = str(canonical["pack_version"])
    expected_hash = hashlib.sha256(archive_pack_directory(pack_dir)).hexdigest()
    public_key = _public_key(manifest_public_key)

    store = PackStore(root / "active")
    valid, valid_reason = asyncio.run(
        _run_candidate(store, valid_manifest_url, public_key, None)
    )
    if not valid:
        raise RuntimeError(f"canonical Findings Pack candidate was rejected: {valid_reason}")
    generation, version, valid_hash = _state(store)
    if version != expected_version:
        raise RuntimeError(f"canonical Findings Pack version changed unexpectedly: {version}")
    if valid_hash != expected_hash:
        raise RuntimeError("activated Findings Pack bytes differ from the canonical smoke payload")
    model_proof = _model_proof(store)

    first_restart = _verify_in_subprocess(
        root,
        expected_generation=generation,
        expected_version=version,
        expected_hash=valid_hash,
    )

    restarted = PackStore(root / "active")
    restarted.initialize()
    rejected, rejection_reason = asyncio.run(
        _run_candidate(restarted, corrupt_manifest_url, public_key, version)
    )
    if rejected:
        raise RuntimeError("corrupt Findings Pack candidate unexpectedly activated")
    if not rejection_reason or "valid JSON" not in rejection_reason:
        raise RuntimeError("corrupt Findings Pack rejection did not identify an unloadable payload")

    final_restart = _verify_in_subprocess(
        root,
        expected_generation=generation,
        expected_version=version,
        expected_hash=valid_hash,
    )

    return {
        "result": "passed",
        "valid_candidate": "canonical-signed-pack",
        "corrupt_candidate": "rejected-unloadable-json",
        "pack_version": version,
        "generation": generation,
        "valid_archive_sha256": valid_hash,
        "retained_archive_sha256": final_restart["archive_sha256"],
        "restart_retained_generation": True,
        "restart_retained_version": True,
        "restart_retained_hash": True,
        "model": model_proof,
        "first_restart": first_restart,
        "after_rejection_restart": final_restart,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--pack-dir", type=Path, default=Path("pack"))
    run_parser.add_argument("--root", type=Path, required=True)
    run_parser.add_argument("--valid-manifest-url", required=True)
    run_parser.add_argument("--corrupt-manifest-url", required=True)
    run_parser.add_argument("--manifest-public-key", required=True)
    run_parser.add_argument("--state-file", type=Path)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--expected-generation", required=True)
    verify_parser.add_argument("--expected-version", required=True)
    verify_parser.add_argument("--expected-hash", required=True)

    args = parser.parse_args(argv)
    if args.command == "verify":
        output = verify_store(
            args.root,
            expected_generation=args.expected_generation,
            expected_version=args.expected_version,
            expected_hash=args.expected_hash,
        )
    else:
        output = run(
            args.pack_dir,
            args.root,
            args.valid_manifest_url,
            args.corrupt_manifest_url,
            args.manifest_public_key,
        )
        if args.state_file is not None:
            args.state_file.parent.mkdir(parents=True, exist_ok=True)
            args.state_file.write_text(
                json.dumps(output, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

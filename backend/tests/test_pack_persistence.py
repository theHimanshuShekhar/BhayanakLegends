from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from bhayanak_legends import config as config_module
from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.credentials import InMemoryCredentialStore

ROOT = Path(__file__).resolve().parents[2]
BUNDLED_PACK = ROOT / "pack"
AUTH = {
    "X-BL-Token": "local-sidecar-development-token-32chars",
    "Host": "127.0.0.1:23110",
}


def _copy_seed(destination: Path) -> Path:
    seed = destination / "bundle" / "pack"
    shutil.copytree(BUNDLED_PACK, seed)
    return seed


def _config(tmp_path: Path) -> SidecarConfig:
    return SidecarConfig(
        token="local-sidecar-development-token-32chars",
        port=23110,
        data_dir=tmp_path / "data",
    )


def test_fresh_install_seeds_durable_active_pack_without_mutating_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    seed = _copy_seed(tmp_path)
    original_pack = (seed / "findings-pack.v1.json").read_bytes()
    monkeypatch.setattr(config_module.sys, "_MEIPASS", str(seed.parent), raising=False)
    config = _config(tmp_path)

    app = create_app(config, credential_store=InMemoryCredentialStore())
    active = config.resolved_active_pack_dir()

    assert (active / "findings-pack.v1.json").read_bytes() == original_pack
    assert (active / "pack.schema.json").read_bytes() == (seed / "pack.schema.json").read_bytes()
    assert (seed / "findings-pack.v1.json").read_bytes() == original_pack
    with TestClient(app) as client:
        response = client.get("/health", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["pack_version"] == "v1"


def test_existing_active_pack_wins_over_changed_bundled_seed(tmp_path: Path, monkeypatch) -> None:
    seed = _copy_seed(tmp_path)
    monkeypatch.setattr(config_module.sys, "_MEIPASS", str(seed.parent), raising=False)
    config = _config(tmp_path)

    create_app(config, credential_store=InMemoryCredentialStore())
    active = config.resolved_active_pack_dir()
    original_active = (active / "findings-pack.v1.json").read_bytes()
    changed = json.loads((seed / "findings-pack.v1.json").read_text())
    changed["pack_version"] = "v9"
    (seed / "findings-pack.v1.json").write_text(json.dumps(changed))

    restarted = create_app(config, credential_store=InMemoryCredentialStore())

    assert (active / "findings-pack.v1.json").read_bytes() == original_active
    assert restarted.state.pack.version() == "v1"


def test_active_pack_survives_restart_without_bundle(tmp_path: Path, monkeypatch) -> None:
    seed = _copy_seed(tmp_path)
    monkeypatch.setattr(config_module.sys, "_MEIPASS", str(seed.parent), raising=False)
    config = _config(tmp_path)

    create_app(config, credential_store=InMemoryCredentialStore())
    shutil.rmtree(seed.parent)
    monkeypatch.setattr(config_module.sys, "_MEIPASS", str(tmp_path / "gone"), raising=False)

    restarted = create_app(config, credential_store=InMemoryCredentialStore())

    assert restarted.state.pack.version() == "v1"
    assert config.resolved_active_pack_dir().is_dir()


def test_invalid_seed_does_not_commit_partial_active_directory(tmp_path: Path, monkeypatch) -> None:
    seed = _copy_seed(tmp_path)
    (seed / "findings-pack.v1.json").write_text("not json")
    monkeypatch.setattr(config_module.sys, "_MEIPASS", str(seed.parent), raising=False)
    config = _config(tmp_path)

    app = create_app(config, credential_store=InMemoryCredentialStore())
    active = config.resolved_active_pack_dir()

    assert app.state.pack_error is not None
    assert not active.exists()
    assert not list(active.parent.glob(f".{active.name}-seed-*"))


def test_model_invalid_seed_does_not_commit_active_directory(tmp_path: Path, monkeypatch) -> None:
    seed = _copy_seed(tmp_path)
    pack_path = seed / "findings-pack.v1.json"
    pack = json.loads(pack_path.read_text())
    pack["provenance"]["dataset"]["feature_contract_version"] = "wrong-contract"
    pack_path.write_text(json.dumps(pack))
    monkeypatch.setattr(config_module.sys, "_MEIPASS", str(seed.parent), raising=False)
    config = _config(tmp_path)

    app = create_app(config, credential_store=InMemoryCredentialStore())

    assert app.state.pack_error is not None
    assert not config.resolved_active_pack_dir().exists()

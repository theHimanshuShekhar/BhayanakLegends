import base64
import sys
from pathlib import Path

import pytest

from bhayanak_legends.credentials import (
    CredentialStore,
    CredentialUnavailableError,
    InMemoryCredentialStore,
)
from bhayanak_legends.store import Store


class FakeDPAPI:
    def __init__(self) -> None:
        self.protect_calls = 0
        self.unprotect_calls = 0
    def protect(self, plaintext: str) -> bytes:
        self.protect_calls += 1
        return b"ciphertext:" + base64.b64encode(plaintext.encode("utf-8"))

    def unprotect(self, ciphertext: bytes) -> str:
        self.unprotect_calls += 1
        return base64.b64decode(ciphertext.removeprefix(b"ciphertext:")).decode("utf-8")


def test_save_load_delete_stores_ciphertext(tmp_path: Path):
    store = Store(tmp_path / "app.db")
    dpapi = FakeDPAPI()
    credentials = CredentialStore(store, protector=dpapi, platform_name="win32")

    credentials.save("RGAPI-secret")
    raw = store.get_raw_setting("riot_key")
    assert isinstance(raw, bytes)
    assert b"RGAPI-secret" not in raw
    assert credentials.has_key() is True
    assert dpapi.unprotect_calls == 0
    assert credentials.load() == "RGAPI-secret"

    credentials.delete()
    assert credentials.has_key() is False
    assert store.get_raw_setting("riot_key") is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_real_windows_dpapi_roundtrip_and_ciphertext(tmp_path: Path):
    store = Store(tmp_path / "app.db")
    credentials = CredentialStore(store)
    secret = "RGAPI-native-windows-secret"

    credentials.save(secret)
    raw = store.get_raw_setting("riot_key")
    assert isinstance(raw, bytes)
    assert secret.encode("utf-8") not in raw
    assert credentials.load() == secret

    credentials.delete()
    assert store.get_raw_setting("riot_key") is None


def test_plaintext_row_migrates_once_on_successful_access(tmp_path: Path):
    store = Store(tmp_path / "app.db")
    store.set_setting("riot_key", "legacy-secret")
    dpapi = FakeDPAPI()
    credentials = CredentialStore(store, protector=dpapi)

    assert credentials.load() == "legacy-secret"
    assert dpapi.protect_calls == 1
    migrated = store.get_raw_setting("riot_key")
    assert isinstance(migrated, bytes)
    assert b"legacy-secret" not in migrated

    assert credentials.load() == "legacy-secret"
    assert dpapi.protect_calls == 1


def test_non_windows_requires_explicit_insecure_opt_in(tmp_path: Path):
    store = Store(tmp_path / "app.db")
    with pytest.raises(CredentialUnavailableError, match="Windows"):
        CredentialStore(store, platform_name="linux").save("dev-secret")

    insecure = InMemoryCredentialStore()
    insecure.save("dev-secret")
    assert insecure.load() == "dev-secret"


def test_insecure_store_requires_opt_in_and_is_blocked_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("BHAYANAK_ALLOW_INSECURE_CREDENTIALS", "1")
    store = Store(tmp_path / "app.db")
    with pytest.warns(RuntimeWarning, match="INSECURE"):
        credentials = CredentialStore(store, platform_name="linux")
    credentials.save("dev-secret")
    assert credentials.load() == "dev-secret"

    monkeypatch.setattr("sys.frozen", True, raising=False)
    frozen = CredentialStore(Store(tmp_path / "frozen.db"), platform_name="linux")
    with pytest.raises(CredentialUnavailableError):
        frozen.save("dev-secret")

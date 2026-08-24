"""Protected storage for the user's permanent Riot API key.

The Windows implementation uses user-scoped DPAPI directly through ``ctypes``.
The credential store is the only module that handles the Riot key at rest.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import warnings
from ctypes import wintypes
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .store import Store

log = logging.getLogger(__name__)

_BLOB_PREFIX = b"BL-DPAPI\x01"
_INSECURE_ENV = "BHAYANAK_ALLOW_INSECURE_CREDENTIALS"


class CredentialError(RuntimeError):
    """Base class for credential storage failures."""


class CredentialUnavailableError(CredentialError):
    """Raised when protected credential storage cannot be used on this host."""


class CredentialBackend(Protocol):
    def save(self, riot_key: str) -> None: ...

    def load(self) -> str | None: ...

    def delete(self) -> None: ...

    def has_key(self) -> bool: ...


class CredentialProtector(Protocol):
    def protect(self, plaintext: str) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> str: ...


class _UnavailableProtector:
    def __init__(self, platform_name: str) -> None:
        self._platform_name = platform_name

    def _error(self) -> CredentialUnavailableError:
        if self._platform_name != "win32":
            return CredentialUnavailableError(
                "Protected Riot key storage requires Windows DPAPI; "
                f"{self._platform_name} is unsupported. Set {_INSECURE_ENV}=1 "
                "only for local development."
            )
        return CredentialUnavailableError("Windows DPAPI credential storage is unavailable")

    def protect(self, plaintext: str) -> bytes:
        raise self._error()

    def unprotect(self, ciphertext: bytes) -> str:
        raise self._error()


class _PlaintextProtector:
    """Development-only plaintext backend, never available in frozen builds."""

    def protect(self, plaintext: str) -> bytes:
        return plaintext.encode("utf-8")

    def unprotect(self, ciphertext: bytes) -> str:
        return ciphertext.decode("utf-8")


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class _WindowsDPAPI:
    """User-scoped CryptProtectData/CryptUnprotectData adapter."""

    def __init__(self) -> None:
        try:
            self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError) as exc:
            raise CredentialUnavailableError("Windows DPAPI credential storage is unavailable") from exc

        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DATA_BLOB),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DATA_BLOB),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    @staticmethod
    def _input_blob(value: bytes):
        buffer = ctypes.create_string_buffer(value)
        blob = _DATA_BLOB(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        return blob, buffer

    def _free(self, blob: _DATA_BLOB) -> None:
        if blob.pbData:
            self._kernel32.LocalFree(ctypes.cast(blob.pbData, wintypes.HLOCAL))

    def protect(self, plaintext: str) -> bytes:
        source, keepalive = self._input_blob(plaintext.encode("utf-8"))
        result = _DATA_BLOB()
        if not self._crypt32.CryptProtectData(
            ctypes.byref(source), "Bhayanak Legends Riot key", None, None, None, 0, ctypes.byref(result)
        ):
            raise CredentialError("Windows DPAPI could not protect the Riot key")
        try:
            return ctypes.string_at(result.pbData, result.cbData)
        finally:
            self._free(result)
            del keepalive

    def unprotect(self, ciphertext: bytes) -> str:
        source, keepalive = self._input_blob(ciphertext)
        result = _DATA_BLOB()
        description = wintypes.LPWSTR()
        if not self._crypt32.CryptUnprotectData(
            ctypes.byref(source), ctypes.byref(description), None, None, None, 0, ctypes.byref(result)
        ):
            raise CredentialError("Windows DPAPI could not unprotect the Riot key")
        try:
            return ctypes.string_at(result.pbData, result.cbData).decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise CredentialError("Windows DPAPI returned an invalid Riot key") from exc
        finally:
            self._free(result)
            if description:
                self._kernel32.LocalFree(ctypes.cast(description, wintypes.HLOCAL))
            del keepalive


class CredentialStore:
    """Store and retrieve the Riot key without exposing storage details."""

    def __init__(
        self,
        store: Store,
        *,
        protector: CredentialProtector | None = None,
        platform_name: str | None = None,
    ) -> None:
        self._store = store
        platform_name = platform_name or sys.platform
        if protector is not None:
            self._protector = protector
        elif platform_name == "win32":
            try:
                self._protector = _WindowsDPAPI()
            except CredentialUnavailableError:
                self._protector = _UnavailableProtector(platform_name)
        elif os.environ.get(_INSECURE_ENV) == "1" and not getattr(sys, "frozen", False):
            warnings.warn(
                "INSECURE Riot key storage enabled; use only on a local development machine",
                RuntimeWarning,
                stacklevel=2,
            )
            log.warning("INSECURE Riot key storage enabled for local development")
            self._protector = _PlaintextProtector()
        else:
            self._protector = _UnavailableProtector(platform_name)

    def save(self, riot_key: str) -> None:
        protected = self._protector.protect(riot_key)
        self._store.set_raw_setting("riot_key", _BLOB_PREFIX + protected)

    def load(self) -> str | None:
        raw = self._store.get_raw_setting("riot_key")
        if raw is None:
            return None
        if isinstance(raw, str):
            # Legacy rows were plaintext. Migrate only after protection succeeds.
            protected = self._protector.protect(raw)
            self._store.set_raw_setting("riot_key", _BLOB_PREFIX + protected)
            return raw
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        if isinstance(raw, bytes) and raw.startswith(_BLOB_PREFIX):
            return self._protector.unprotect(raw[len(_BLOB_PREFIX) :])
        if isinstance(raw, bytes):
            # Be tolerant of a legacy UTF-8 BLOB created by an older SQLite client.
            try:
                legacy = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise CredentialError("Stored Riot key has an unsupported format") from None
            protected = self._protector.protect(legacy)
            self._store.set_raw_setting("riot_key", _BLOB_PREFIX + protected)
            return legacy
        raise CredentialError("Stored Riot key has an unsupported format")

    def delete(self) -> None:
        self._store.delete_raw_setting("riot_key")

    def has_key(self) -> bool:
        # Presence is intentionally derived from SQLite metadata; no decryption occurs.
        return self._store.has_setting("riot_key")


class InMemoryCredentialStore:
    """Explicit test seam for environments where Windows DPAPI is unavailable."""

    def __init__(self) -> None:
        self._riot_key: str | None = None

    def save(self, riot_key: str) -> None:
        self._riot_key = riot_key

    def load(self) -> str | None:
        return self._riot_key

    def delete(self) -> None:
        self._riot_key = None

    def has_key(self) -> bool:
        return self._riot_key is not None

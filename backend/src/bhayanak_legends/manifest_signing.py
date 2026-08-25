"""Pinned Ed25519 verification for Findings Pack release manifests."""

from __future__ import annotations

import base64
import binascii
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# This key is part of the application release. Rotate it only as part of an
# application release, together with the publishing secret and delivery ADR.
PINNED_MANIFEST_PUBLIC_KEY_B64: Final = "yHtpqTMZhbCf2l61USHtx2bShhM1x7PVttXDs86jtDI="
PINNED_MANIFEST_PUBLIC_KEY: Final = base64.b64decode(PINNED_MANIFEST_PUBLIC_KEY_B64)


class ManifestSignatureError(ValueError):
    """A detached manifest signature could not authenticate the raw bytes."""


def _decode_signature(signature: bytes) -> bytes:
    """Decode a raw or base64-encoded 64-byte Ed25519 signature."""
    if not signature or len(signature) > 16 * 1024:
        raise ManifestSignatureError("release manifest signature is missing or too large")
    if len(signature) == 64:
        return signature
    try:
        decoded = base64.b64decode(signature.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ManifestSignatureError("release manifest signature is malformed") from exc
    if len(decoded) != 64:
        raise ManifestSignatureError("release manifest signature is malformed")
    return decoded


def verify_manifest_signature(
    manifest: bytes,
    signature: bytes,
    *,
    public_key: bytes = PINNED_MANIFEST_PUBLIC_KEY,
) -> None:
    """Verify a detached signature over the exact raw manifest bytes.

    The production default is pinned in this module. The explicit key seam is
    only for deterministic tests and never reads key material from the manifest.
    """
    detached = _decode_signature(signature)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(detached, manifest)
    except (InvalidSignature, ValueError) as exc:
        raise ManifestSignatureError("release manifest signature is invalid") from exc


__all__ = [
    "ManifestSignatureError",
    "PINNED_MANIFEST_PUBLIC_KEY",
    "PINNED_MANIFEST_PUBLIC_KEY_B64",
    "verify_manifest_signature",
]

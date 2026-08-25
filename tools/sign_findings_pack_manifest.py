#!/usr/bin/env python3
"""Sign the exact bytes of a Findings Pack release manifest.

The CI signing key is supplied through FINDINGS_PACK_MANIFEST_SIGNING_KEY as
base64 (or hexadecimal) seed bytes. It is never accepted from the manifest.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def _private_key(value: str) -> bytes:
    value = value.strip()
    try:
        if len(value) == 64:
            raw = bytes.fromhex(value)
        else:
            raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SystemExit("FINDINGS_PACK_MANIFEST_SIGNING_KEY is not valid key material") from exc
    if len(raw) != 32:
        raise SystemExit("FINDINGS_PACK_MANIFEST_SIGNING_KEY must contain a 32-byte seed")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    secret = os.environ.get("FINDINGS_PACK_MANIFEST_SIGNING_KEY")
    if not secret:
        raise SystemExit("FINDINGS_PACK_MANIFEST_SIGNING_KEY is required")
    try:
        raw = args.manifest.read_bytes()
    except OSError as exc:
        raise SystemExit(f"cannot read manifest: {exc}") from exc
    output = args.output or args.manifest.with_name(args.manifest.name + ".sig")
    try:
        output.write_bytes(
            base64.b64encode(Ed25519PrivateKey.from_private_bytes(_private_key(secret)).sign(raw)) + b"\n"
        )
    except OSError as exc:
        raise SystemExit(f"cannot write signature: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Copy smoke diagnostics while removing credential-shaped values.

Beyond generic secret assignments and Riot keys, redaction strips:

- ``tauri signer``-issued key/signature material. That CLI writes private
  keys, public keys, and detached signatures as a single line of base64 text
  that always decodes to a minisign ``untrusted comment: ...`` block, so any
  such blob is redacted by its stable base64 prefix wherever it appears
  (standalone key files, or embedded as a JSON string value such as
  ``tauri.conf.json``'s ``pubkey`` field).
- PEM private-key blocks, password/secret/token assignments (including
  underscore-joined names such as ``TAURI_SIGNING_PRIVATE_KEY_PASSWORD``),
  Riot API keys, and token-bearing query strings.
- Any literal extra secret supplied via ``REDACT_EXTRA_SECRETS``
  (whitespace-separated, provided only by the job that owns the values).

Directory separation is the primary control: ephemeral key files and the
production-config backup live outside the diagnostics tree that this tool
copies, so they are never candidates for upload regardless of redaction.
This tool is defense in depth for whatever text does get written there.
Binary or undecodable files are copied verbatim only when they cannot be
read as text; everything else passes through the redactors.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil

SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:token|password|passphrase|secret|private[_-]?key|api[_-]?key)[a-z_]*\s*[:=]\s*[\"']?)"
    r"([^\"'\s,}]+)"
)
RIOT_KEY = re.compile(r"\bRGAPI-[A-Za-z0-9_-]+\b")
TOKEN_QUERY = re.compile(r"(?i)([?&](?:token|access_token|api_key)=)[^&\s\"']+")
PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
)
# base64("untrusted comment:") — the fixed prefix every tauri-signer key or
# signature file starts with, regardless of whether it holds a private key,
# a public key, or a detached signature.
MINISIGN_ARMORED_BASE64 = re.compile(r"dW50cnVzdGVkIGNvbW1lbnQ6[A-Za-z0-9+/]+=*")


def extra_secrets(env_value: str | None) -> list[str]:
    if not env_value:
        return []
    return [value for value in env_value.split() if len(value) >= 8]


def redact(text: str, extras: list[str] | None = None) -> str:
    text = PEM_PRIVATE_KEY.sub("[REDACTED PRIVATE KEY BLOCK]", text)
    text = MINISIGN_ARMORED_BASE64.sub("[REDACTED MINISIGN KEY MATERIAL]", text)
    text = TOKEN_QUERY.sub(r"\1[REDACTED]", text)
    text = SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = RIOT_KEY.sub("RGAPI-[REDACTED]", text)
    for value in extras or []:
        text = text.replace(value, "[REDACTED]")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    extras = extra_secrets(os.environ.get("REDACT_EXTRA_SECRETS"))
    args.destination.mkdir(parents=True, exist_ok=True)
    if not args.source.exists():
        return
    for source in args.source.rglob("*"):
        if not source.is_file():
            continue
        target = args.destination / source.relative_to(args.source)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            shutil.copyfile(source, target)
            continue
        target.write_text(redact(text, extras), encoding="utf-8")


if __name__ == "__main__":
    main()

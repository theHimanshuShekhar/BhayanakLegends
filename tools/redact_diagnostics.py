"""Copy smoke diagnostics while removing credential-shaped values.

Diagnostics are untrusted process output.  Text values matching secret,
public-key, or token assignments are replaced before upload; files that look
like key material are represented by a fixed marker instead of copied raw.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re


SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:[A-Za-z0-9]+[_-])*(?:token|password|secret|private[_-]?key|api[_-]?key)"
    r"\b\s*[:=]\s*[\"']?)([^\"'\s,};]+)"
)
PUBLIC_KEY_ASSIGNMENT = re.compile(
    r"(?i)((?:[A-Za-z0-9]+[_-])*(?:public[_-]?key|pubkey|production[_-]?key|updater[_-]?key)"
    r"\b\s*[:=]\s*[\"']?)([^\"'\s,};]+)"
)
BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
QUERY_TOKEN = re.compile(
    r"(?i)([?&](?:access[_-]?)?token=)[^&#\s]+"
)
TOKEN_SHAPES = re.compile(
    r"\b(?:ghp|github_pat|glpat|xox[baprs])_[A-Za-z0-9._-]+\b"
)
RIOT_KEY = re.compile(r"\bRGAPI-[A-Za-z0-9_-]+\b")
KEY_FILE_NAME = re.compile(
    r"(?i)(?:private|public|production|updater|signing|secret|password|token).*(?:key|pem)"
)


def redact(text: str) -> str:
    text = SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = PUBLIC_KEY_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = BEARER_TOKEN.sub("Bearer [REDACTED]", text)
    text = QUERY_TOKEN.sub(r"\1[REDACTED]", text)
    text = TOKEN_SHAPES.sub("[REDACTED_TOKEN]", text)
    return RIOT_KEY.sub("RGAPI-[REDACTED]", text)


def _safe_name(path: Path) -> bool:
    return KEY_FILE_NAME.search(path.name) is None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.destination.is_symlink():
        raise SystemExit("diagnostic destination must not be a symlink")
    if args.source.is_symlink():
        raise SystemExit("diagnostic source must not be a symlink")
    source_root = args.source.resolve()
    destination_root = args.destination.resolve()
    try:
        destination_root.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise SystemExit("diagnostic destination must be outside its source")
    args.destination.mkdir(parents=True, exist_ok=True)
    if not args.source.exists():
        return
    for source in args.source.rglob("*"):
        if source.is_symlink() or not source.is_file():
            continue
        target = args.destination / source.relative_to(args.source)
        if target.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not _safe_name(source):
            target.write_text("[REDACTED KEY MATERIAL]\n", encoding="utf-8")
            continue
        try:
            raw = source.read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-8", errors="replace")
        target.write_text(redact(text), encoding="utf-8")


if __name__ == "__main__":
    main()

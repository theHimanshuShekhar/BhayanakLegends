"""Copy smoke diagnostics while removing common credential-shaped values."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:token|password|secret|private[_-]?key|api[_-]?key)\b\s*[:=]\s*[\"']?)([^\"'\s,}]+)"
)
RIOT_KEY = re.compile(r"\bRGAPI-[A-Za-z0-9_-]+\b")


def redact(text: str) -> str:
    text = SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    return RIOT_KEY.sub("RGAPI-[REDACTED]", text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    if not args.source.exists():
        return
    for source in args.source.rglob("*"):
        if not source.is_file():
            continue
        target = args.destination / source.relative_to(args.source)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(redact(source.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
        except OSError:
            shutil.copyfile(source, target)


if __name__ == "__main__":
    main()

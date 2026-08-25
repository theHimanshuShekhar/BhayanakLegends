"""Canonical filesystem validation for the development import boundary."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class ImportPathError(ValueError):
    """Base error raised when a development import path cannot be accepted."""

    detail: str

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidImportDirectoryError(ImportPathError):
    """The requested import path does not exist as a directory."""

    def __init__(self) -> None:
        super().__init__("invalid import directory")


class ImportPathNotApprovedError(ImportPathError):
    """The requested import path is outside every configured approved root."""

    def __init__(self) -> None:
        super().__init__("import path not approved")


def canonical_import_roots(approved_roots: Iterable[Path]) -> tuple[Path, ...]:
    """Return existing configured roots after resolving symlinks."""
    canonical_roots: list[Path] = []
    for root in approved_roots:
        try:
            canonical_roots.append(Path(root).resolve(strict=True))
        except (FileNotFoundError, OSError, RuntimeError):
            continue
    return tuple(canonical_roots)


def canonical_import_directory(
    directory: Path,
    approved_roots: Iterable[Path],
) -> Path:
    """Validate and return a requested import directory in canonical form.

    Both the request and each configured root are resolved with symlinks followed
    before comparing path components. A missing/non-directory request retains
    its distinct validation error so callers can report the exact contract
    detail.
    """
    try:
        canonical_directory = Path(directory).resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        raise InvalidImportDirectoryError from None
    if not canonical_directory.is_dir():
        raise InvalidImportDirectoryError

    for canonical_root in canonical_import_roots(approved_roots):
        try:
            canonical_directory.relative_to(canonical_root)
        except ValueError:
            continue
        return canonical_directory

    raise ImportPathNotApprovedError

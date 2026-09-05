"""Hash verification helpers for bundled wheel payload/data artifacts."""

import hashlib
from pathlib import Path
from typing import Iterable

from app.errors import DataIntegrityError


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> str:
    if not expected or len(expected) != 64:
        raise DataIntegrityError(f"missing or malformed SHA-256 for {path}")
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise DataIntegrityError(
            f"SHA-256 mismatch for {path}: expected {expected}, got {actual}"
        )
    return actual


def sha256_tree(root: Path) -> str:
    """Hash a payload deterministically by relative POSIX path and bytes."""

    if not root.is_dir():
        raise DataIntegrityError(f"payload directory is missing: {root}")
    digest = hashlib.sha256()
    for path in sorted(_files(root), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _files(root: Path) -> Iterable[Path]:
    return (path for path in root.rglob("*") if path.is_file())


def verify_tree_sha256(root: Path, expected: str) -> str:
    if not expected or len(expected) != 64:
        raise DataIntegrityError(f"missing or malformed payload SHA-256 for {root}")
    actual = sha256_tree(root)
    if actual.lower() != expected.lower():
        raise DataIntegrityError(
            f"payload SHA-256 mismatch for {root}: expected {expected}, got {actual}"
        )
    return actual

#!/usr/bin/env python3
"""Deterministic path policy and derivation helpers for OpenCC runtime payloads."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
from typing import Iterable, Mapping


SUBSET_RECIPE = "runtime-subset-v1"
_KEEP_EXACT = {
    "opencc/__init__.py",
    "opencc/cli.py",
    "opencc/py.typed",
    "opencc/clib/__init__.py",
    "opencc-1.4.2.dist-info/METADATA",
    "opencc-1.4.2.dist-info/WHEEL",
    "opencc-1.4.2.dist-info/RECORD",
    "opencc-1.4.2.dist-info/top_level.txt",
    "opencc-1.4.2.dist-info/entry_points.txt",
}
_KEEP_JIEBA_FILES = {
    "hmm_model.utf8",
    "idf.utf8",
    "jieba_merged.ocd2",
    "stop_words.utf8",
}
_REMOVED_JIEBA_FILES = {"jieba.dict.utf8", "user.dict.utf8"}
_HEX = frozenset("0123456789abcdefABCDEF")


class RuntimeSubsetError(ValueError):
    """Raised when a wheel contains a path outside the reviewed subset policy."""


def _safe_relative(value: str, *, label: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or "" in path.parts
        or path.as_posix() != value
    ):
        raise RuntimeSubsetError(f"unsafe {label}: {value!r}")
    return path.as_posix()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in _HEX for character in value)


def _native_library(plugin_dir: str, library_path: str) -> tuple[str, str]:
    plugin_dir = _safe_relative(plugin_dir, label="native plugin directory")
    library_path = _safe_relative(library_path, label="native plugin library")
    if PurePosixPath(library_path).parent.as_posix() != plugin_dir:
        raise RuntimeSubsetError("native plugin library must be a direct child of plugin_dir")
    if not library_path.startswith("opencc/"):
        raise RuntimeSubsetError("native plugin library must be inside the OpenCC wheel")
    return plugin_dir, library_path


def classify_path(relative: str, *, plugin_dir: str, library_path: str) -> str:
    """Return ``keep``, ``exclude``, or ``unknown`` for one wheel-relative path."""

    relative = _safe_relative(relative, label="payload path")
    plugin_dir, library_path = _native_library(plugin_dir, library_path)
    path = PurePosixPath(relative)
    parts = path.parts
    name = path.name

    if relative == library_path:
        return "keep"
    if relative.startswith(plugin_dir + "/"):
        return "unknown"
    if relative in _KEEP_EXACT:
        return "keep"
    if relative.startswith("opencc.libs/"):
        return "keep"
    if (
        len(parts) == 2
        and parts[0] == "opencc-1.4.2.dist-info"
        and name in {"METADATA", "WHEEL", "RECORD", "top_level.txt", "entry_points.txt"}
    ):
        return "keep"
    if relative.startswith("opencc-1.4.2.dist-info/licenses/"):
        return "keep"
    if len(parts) == 3 and parts[:2] == ("opencc", "clib"):
        if name.startswith("opencc_clib") and path.suffix.lower() in {".so", ".pyd"}:
            return "keep"
    if len(parts) == 5 and parts[:4] == (
        "opencc",
        "clib",
        "share",
        "opencc",
    ):
        if path.suffix.lower() in {".json", ".ocd2"}:
            return "keep"
    if len(parts) == 6 and parts[:5] == (
        "opencc",
        "clib",
        "share",
        "opencc",
        "jieba_dict",
    ):
        if name in _KEEP_JIEBA_FILES:
            return "keep"
        if name in _REMOVED_JIEBA_FILES:
            return "exclude"

    lower_parts = tuple(part.casefold() for part in parts)
    if len(parts) >= 4 and parts[:3] == ("opencc", "clib", "bin"):
        return "exclude"
    if len(parts) >= 4 and parts[:3] == ("opencc", "clib", "include"):
        return "exclude"
    if len(parts) >= 4 and parts[:3] in {
        ("opencc", "clib", "lib"),
        ("opencc", "clib", "lib64"),
    }:
        return "exclude"
    if path.suffix.casefold() in {".a", ".lib"}:
        return "exclude"
    if "cmake" in lower_parts or "pkgconfig" in lower_parts:
        return "exclude"

    return "unknown"


def _all_files(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _all_files(root):
        relative = path.relative_to(root).as_posix()
        if path.suffix in {".pyc", ".pyo"} or "__pycache__" in PurePosixPath(relative).parts:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _plan(root: Path, *, plugin_dir: str, library_path: str) -> tuple[list[Path], list[dict[str, object]]]:
    keep: list[Path] = []
    removed: list[dict[str, object]] = []
    unknown: list[str] = []
    symlinks = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_symlink()
    )
    if symlinks:
        raise RuntimeSubsetError("symbolic links are not allowed in OpenCC wheels: " + ", ".join(symlinks[:20]))
    for path in _all_files(root):
        relative = path.relative_to(root).as_posix()
        kind = classify_path(relative, plugin_dir=plugin_dir, library_path=library_path)
        if kind == "keep":
            keep.append(path)
        elif kind == "exclude":
            removed.append(
                {
                    "path": relative,
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                }
            )
        else:
            unknown.append(relative)
    if unknown:
        raise RuntimeSubsetError(
            "unreviewed OpenCC wheel files: " + ", ".join(sorted(unknown)[:20])
        )
    return keep, removed


def validate_runtime_subset_paths(
    paths: Iterable[str], *, plugin_dir: str, library_path: str
) -> None:
    """Require all files in a published runtime payload to be allowlisted."""

    unknown: list[str] = []
    excluded: list[str] = []
    normalized: list[str] = []
    for value in paths:
        relative = _safe_relative(str(value), label="payload path")
        normalized.append(relative)
        kind = classify_path(relative, plugin_dir=plugin_dir, library_path=library_path)
        if kind == "unknown":
            unknown.append(relative)
        elif kind == "exclude":
            excluded.append(relative)
    if unknown:
        raise RuntimeSubsetError("unreviewed OpenCC runtime files: " + ", ".join(sorted(unknown)[:20]))
    if excluded:
        raise RuntimeSubsetError("excluded OpenCC files are present: " + ", ".join(sorted(excluded)[:20]))
    required = _KEEP_EXACT
    missing = sorted(required - set(normalized))
    if missing:
        raise RuntimeSubsetError("required OpenCC runtime files are missing: " + ", ".join(missing))
    if not any(
        PurePosixPath(path).parts[:2] == ("opencc", "clib")
        and PurePosixPath(path).name.startswith("opencc_clib")
        and PurePosixPath(path).suffix.lower() in {".so", ".pyd"}
        for path in normalized
    ):
        raise RuntimeSubsetError("OpenCC runtime binding library is missing")
    plugin_dir, library_path = _native_library(plugin_dir, library_path)
    if library_path not in normalized:
        raise RuntimeSubsetError(f"native plugin library is missing: {library_path}")
    if not any(path.startswith("opencc-1.4.2.dist-info/licenses/") for path in normalized):
        raise RuntimeSubsetError("OpenCC wheel license directory is missing")


def export_runtime_subset(
    source_root: Path,
    destination: Path,
    *,
    plugin_dir: str,
    library_path: str,
) -> tuple[str, list[dict[str, object]]]:
    """Copy an allowlisted subset and return its tree hash and removal receipt."""

    source_resolved = source_root.resolve()
    destination_resolved = destination.resolve()
    if (
        source_resolved == destination_resolved
        or source_resolved in destination_resolved.parents
        or destination_resolved in source_resolved.parents
    ):
        raise RuntimeSubsetError("runtime subset destination must not overlap its source tree")
    keep, removed = _plan(source_root, plugin_dir=plugin_dir, library_path=library_path)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in keep:
        relative = path.relative_to(source_root)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, output)
    kept_names = [path.relative_to(source_root).as_posix() for path in keep]
    validate_runtime_subset_paths(kept_names, plugin_dir=plugin_dir, library_path=library_path)
    return sha256_tree(destination), removed


def derive_record(
    record: Mapping[str, object],
    source_root: Path,
    destination: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    """Copy one full tested payload and rewrite its record for the derived tree."""

    derived = dict(record)
    native = derived.get("native_plugins")
    plugin = native.get("opencc-jieba") if isinstance(native, dict) else None
    if not isinstance(plugin, dict):
        raise RuntimeSubsetError("official native opencc-jieba record is missing")
    source_tree_hash = sha256_tree(source_root)
    if source_tree_hash.lower() != str(derived.get("payload_sha256", "")).lower():
        raise RuntimeSubsetError("full source payload hash does not match its manifest record")
    payload_hash, removed = export_runtime_subset(
        source_root,
        destination,
        plugin_dir=str(plugin.get("plugin_dir", "")),
        library_path=str(plugin.get("library_path", "")),
    )
    data_root = destination / "opencc" / "clib" / "share" / "opencc"
    data_files = {
        path.relative_to(destination).as_posix(): sha256_file(path)
        for path in sorted(data_root.rglob("*"))
        if path.is_file()
    }
    config_data = dict(derived.get("config_data", {}))
    config_data["files"] = data_files
    config_data["manifest_sha256"] = hashlib.sha256(
        json.dumps(data_files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    derived["config_data"] = config_data

    filtered_native = {name: dict(value) for name, value in native.items()}
    filtered_plugin = filtered_native["opencc-jieba"]
    resources = {
        _safe_relative(str(relative), label="native plugin resource"): str(digest)
        for relative, digest in filtered_plugin.get("resource_hashes", {}).items()
        if (destination / _safe_relative(str(relative), label="native plugin resource")).is_file()
    }
    filtered_plugin["resource_hashes"] = resources
    filtered_plugin["resource_manifest_sha256"] = hashlib.sha256(
        json.dumps(resources, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    derived["native_plugins"] = filtered_native
    derived["payload_sha256"] = payload_hash
    derived["record_describes"] = "source_wheel"
    derived["derivation"] = {
        "recipe": SUBSET_RECIPE,
        "source_wheel_sha256": str(derived["wheel_sha256"]),
        "source_tree_sha256": source_tree_hash,
        "removed": removed,
    }
    exported = {
        "payload_sha256": payload_hash,
        "source_tree_sha256": source_tree_hash,
        "removed": removed,
        "config_data": config_data,
        "native_plugins": filtered_native,
    }
    return derived, exported


def validate_derivation(
    record: Mapping[str, object],
    *,
    kept_paths: Iterable[str],
    plugin_dir: str,
    library_path: str,
) -> None:
    """Validate the subset receipt shape and require removed paths be policy-excluded."""

    if record.get("record_describes") != "source_wheel":
        raise RuntimeSubsetError("derived payload record_describes must be 'source_wheel'")
    derivation = record.get("derivation")
    if not isinstance(derivation, Mapping):
        raise RuntimeSubsetError("derived payload derivation is missing")
    if derivation.get("recipe") != SUBSET_RECIPE:
        raise RuntimeSubsetError("unsupported runtime subset derivation recipe")
    wheel_hash = str(record.get("wheel_sha256", "")).lower()
    source_wheel_hash = str(derivation.get("source_wheel_sha256", "")).lower()
    if not _is_sha256(wheel_hash) or source_wheel_hash != wheel_hash:
        raise RuntimeSubsetError("derivation source_wheel_sha256 does not match wheel_sha256")
    source_tree_hash = derivation.get("source_tree_sha256")
    if not _is_sha256(source_tree_hash):
        raise RuntimeSubsetError("derivation source_tree_sha256 is malformed")
    removed = derivation.get("removed")
    if not isinstance(removed, list):
        raise RuntimeSubsetError("derivation removed must be a list")
    removed_paths: list[str] = []
    for entry in removed:
        if not isinstance(entry, Mapping):
            raise RuntimeSubsetError("derivation removed entries must be objects")
        relative = _safe_relative(str(entry.get("path", "")), label="removed path")
        digest = entry.get("sha256")
        size = entry.get("size")
        if not _is_sha256(digest) or not isinstance(size, int) or size < 0:
            raise RuntimeSubsetError(f"malformed removed file receipt: {relative}")
        if classify_path(relative, plugin_dir=plugin_dir, library_path=library_path) != "exclude":
            raise RuntimeSubsetError(f"removed path is not excluded by policy: {relative}")
        removed_paths.append(relative)
    if removed_paths != sorted(set(removed_paths)):
        raise RuntimeSubsetError("derivation removed paths must be unique and sorted")
    kept = {str(path) for path in kept_paths}
    validate_runtime_subset_paths(kept, plugin_dir=plugin_dir, library_path=library_path)
    overlap = kept.intersection(removed_paths)
    if overlap:
        raise RuntimeSubsetError("derivation marks retained files as removed: " + ", ".join(sorted(overlap)))

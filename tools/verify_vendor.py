#!/usr/bin/env python3
"""Validate the vendored official OpenCC wheel manifest and payload hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "opencc"
MANIFEST = VENDOR_ROOT / "manifest.json"
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
EXPECTED_POLICY = {
    "implementation": "CPython",
    "major": 3,
    "minor": 14,
    "abi": "cp314",
    "production_baseline": "3.14.2",
    "development_ci": "3.14.7",
    "patch_participates_in_payload_selection": False,
}
JIEBA_PLUGIN_NAME = "opencc-jieba"
JIEBA_CONFIGS = (
    "s2t_jieba",
    "s2tw_jieba",
    "s2twp_jieba",
    "s2hk_jieba",
    "s2hkp_jieba",
    "tw2sp_jieba",
    "hk2sp_jieba",
)


def _files(root: Path) -> Iterable[Path]:
    return (path for path in root.rglob("*") if path.is_file())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(_files(root), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _data_manifest(root: Path) -> dict[str, str]:
    share_root = root / "opencc" / "clib" / "share" / "opencc"
    return {
        path.relative_to(root).as_posix(): _sha256_file(path)
        for path in sorted(_files(share_root), key=lambda item: item.relative_to(root).as_posix())
    }


def _canonical_manifest_hash(files: Mapping[str, str]) -> str:
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _payload_root(payload_path: str) -> Path:
    relative = Path(payload_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(f"payload path escapes vendor root: {payload_path!r}")
    root = (VENDOR_ROOT / relative).resolve()
    if VENDOR_ROOT.resolve() not in root.parents:
        raise SystemExit(f"payload path escapes vendor root: {payload_path!r}")
    return root


def _safe_payload_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SystemExit(f"native plugin path escapes payload: {relative!r}")
    resolved = (root / candidate).resolve()
    if root.resolve() not in resolved.parents:
        raise SystemExit(f"native plugin path escapes payload: {relative!r}")
    return resolved


def _validate_native_plugins(
    record: Mapping[str, object],
    root: Path,
    data_files: Mapping[str, str],
    *,
    opencc_version: str,
    upstream_tag: str,
    upstream_commit: str,
) -> None:
    native_plugins = record.get("native_plugins")
    if not isinstance(native_plugins, dict):
        raise SystemExit("payload native_plugins must be an object")
    plugin = native_plugins.get(JIEBA_PLUGIN_NAME)
    if not isinstance(plugin, dict):
        raise SystemExit(
            f"payload must contain the official {JIEBA_PLUGIN_NAME} native plugin record"
        )
    required = {
        "name",
        "kind",
        "upstream_version",
        "upstream_tag",
        "upstream_commit",
        "plugin_dir",
        "library_path",
        "library_sha256",
        "config_names",
        "resource_hashes",
        "resource_manifest_sha256",
        "build_profile",
    }
    missing = sorted(required - set(plugin))
    if missing:
        raise SystemExit("native plugin missing keys: " + ", ".join(missing))
    if plugin["name"] != JIEBA_PLUGIN_NAME or plugin["kind"] != "segmentation":
        raise SystemExit("native plugin record is not the official segmentation plugin")
    if (
        plugin["upstream_version"],
        plugin["upstream_tag"],
        plugin["upstream_commit"],
    ) != (opencc_version, upstream_tag, upstream_commit):
        raise SystemExit("native plugin provenance does not match the OpenCC payload")
    config_names = plugin["config_names"]
    if config_names != list(JIEBA_CONFIGS):
        raise SystemExit(
            f"official {JIEBA_PLUGIN_NAME} config_names must be {list(JIEBA_CONFIGS)!r}"
        )
    plugin_dir = _safe_payload_path(root, str(plugin["plugin_dir"]))
    library = _safe_payload_path(root, str(plugin["library_path"]))
    if not plugin_dir.is_dir():
        raise SystemExit(f"native plugin directory is missing: {plugin_dir}")
    if not library.is_file() or library.parent.resolve() != plugin_dir.resolve():
        raise SystemExit(f"native plugin library is missing or misplaced: {library}")
    if library.suffix.lower() not in {".dll", ".dylib", ".so"}:
        raise SystemExit(f"native plugin library has an unexpected suffix: {library}")
    library_hash = plugin["library_sha256"]
    if not isinstance(library_hash, str) or not HEX64.fullmatch(library_hash):
        raise SystemExit("native plugin library_sha256 is missing or malformed")
    if _sha256_file(library).lower() != library_hash.lower():
        raise SystemExit(f"native plugin library hash mismatch: {library}")

    resource_hashes = plugin["resource_hashes"]
    if not isinstance(resource_hashes, dict) or not resource_hashes:
        raise SystemExit("native plugin resource_hashes must be a non-empty object")
    expected_resource_paths = {
        f"opencc/clib/share/opencc/{config}.json" for config in JIEBA_CONFIGS
    }
    expected_resource_paths.update(
        path for path in data_files if path.startswith("opencc/clib/share/opencc/jieba_dict/")
    )
    if set(resource_hashes) != expected_resource_paths:
        raise SystemExit("native plugin resource list does not match official Jieba resources")
    for relative, digest in resource_hashes.items():
        if not isinstance(relative, str) or not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise SystemExit(f"invalid native plugin resource hash for {relative!r}")
        resource = _safe_payload_path(root, relative)
        if not resource.is_file() or data_files.get(relative) != digest:
            raise SystemExit(f"native plugin resource hash mismatch: {relative}")
    manifest_hash = plugin["resource_manifest_sha256"]
    if not isinstance(manifest_hash, str) or not HEX64.fullmatch(manifest_hash):
        raise SystemExit("native plugin resource_manifest_sha256 is missing or malformed")
    if _canonical_manifest_hash(resource_hashes) != manifest_hash:
        raise SystemExit("native plugin resource manifest hash does not match resources")
    if not isinstance(plugin["build_profile"], str) or not plugin["build_profile"].strip():
        raise SystemExit("native plugin build_profile is missing")


def _validate_payload(
    record: Mapping[str, object],
    *,
    opencc_version: str,
    upstream_tag: str,
    upstream_commit: str,
) -> tuple[str, str]:
    required = {
        "python_implementation",
        "python_version",
        "python_abi",
        "os",
        "architecture",
        "wheel_name",
        "wheel_sha256",
        "payload_path",
        "payload_sha256",
        "config_hashes",
        "config_data",
        "native_plugins",
    }
    missing = sorted(required - set(record))
    if missing:
        raise SystemExit("payload missing keys: " + ", ".join(missing))
    if (
        record["python_implementation"],
        record["python_version"],
        record["python_abi"],
    ) != ("CPython", "3.14", "cp314"):
        raise SystemExit("payload runtime is outside the CPython 3.14.x/cp314 policy")
    for key in ("wheel_sha256", "payload_sha256"):
        if not isinstance(record[key], str) or not HEX64.fullmatch(record[key]):
            raise SystemExit(f"payload {key} must be a SHA-256 hex digest")
    if not isinstance(record["config_hashes"], dict):
        raise SystemExit("payload config_hashes must be an object")
    payload_path = str(record["payload_path"])
    config_data = record["config_data"]
    if not isinstance(config_data, dict):
        raise SystemExit("payload config_data must be an object")
    expected_data_files = config_data.get("files")
    expected_data_hash = config_data.get("manifest_sha256")
    if not isinstance(expected_data_files, dict) or not expected_data_files:
        raise SystemExit(f"payload config_data.files must contain hashes: {payload_path}")
    if not isinstance(expected_data_hash, str) or not HEX64.fullmatch(expected_data_hash):
        raise SystemExit(f"payload config_data.manifest_sha256 is malformed: {payload_path}")
    if _canonical_manifest_hash(expected_data_files) != expected_data_hash:
        raise SystemExit(f"payload config_data.manifest_sha256 does not match: {payload_path}")
    root = _payload_root(payload_path)
    if not root.is_dir():
        raise SystemExit(f"vendored payload is missing: {root}")
    actual_payload_hash = _sha256_tree(root)
    if actual_payload_hash.lower() != str(record["payload_sha256"]).lower():
        raise SystemExit(
            f"payload SHA-256 mismatch for {payload_path}: expected {record['payload_sha256']}, got {actual_payload_hash}"
        )
    actual_data_files = _data_manifest(root)
    if actual_data_files != expected_data_files:
        raise SystemExit(f"payload data/config files differ from the manifest: {payload_path}")
    for config, digest in record["config_hashes"].items():
        if not isinstance(config, str) or not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise SystemExit(f"invalid config hash for {config!r}")
        data_path = f"opencc/clib/share/opencc/{config}.json"
        if actual_data_files.get(data_path) != digest:
            raise SystemExit(f"config hash does not match vendored data for {config!r}")
    _validate_native_plugins(
        record,
        root,
        actual_data_files,
        opencc_version=opencc_version,
        upstream_tag=upstream_tag,
        upstream_commit=upstream_commit,
    )
    return str(record["python_abi"]), f"{record['os']}/{record['architecture']}"


def main() -> int:
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read vendor manifest: {MANIFEST}") from exc
    required = {
        "schema_version",
        "status",
        "opencc_version",
        "distribution_name",
        "import_name",
        "opencc_upstream_tag",
        "opencc_upstream_commit",
        "tofu_policy",
        "provenance_source",
        "python_compatibility",
        "payloads",
        "config_data",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise SystemExit("manifest missing keys: " + ", ".join(missing))
    if payload["schema_version"] != 1:
        raise SystemExit("unsupported manifest schema")
    if payload["distribution_name"] != "opencc" or payload["import_name"] != "opencc":
        raise SystemExit("manifest must describe the official opencc distribution/import")
    if payload["python_compatibility"] != EXPECTED_POLICY:
        raise SystemExit("manifest Python compatibility policy is not CPython 3.14.x/cp314")
    if not isinstance(payload["payloads"], list) or not payload["payloads"]:
        raise SystemExit("manifest must contain at least one verified official OpenCC payload")
    config_data = payload["config_data"]
    if not isinstance(config_data, dict):
        raise SystemExit("manifest config_data must be an object")
    config_payloads = config_data.get("payloads")
    if not isinstance(config_payloads, dict):
        raise SystemExit("manifest config_data.payloads must contain per-payload provenance")

    seen: set[tuple[object, ...]] = set()
    locations: list[str] = []
    for record in payload["payloads"]:
        if not isinstance(record, dict):
            raise SystemExit("manifest payload entries must be objects")
        identity = tuple(
            record.get(key)
            for key in ("python_implementation", "python_version", "python_abi", "os", "architecture")
        )
        if identity in seen:
            raise SystemExit(f"duplicate payload runtime identity: {identity}")
        seen.add(identity)
        payload_path = str(record.get("payload_path", ""))
        if config_payloads.get(payload_path) != record.get("config_data"):
            raise SystemExit(f"manifest config_data does not match payload: {payload_path}")
        _, location = _validate_payload(
            record,
            opencc_version=str(payload["opencc_version"]),
            upstream_tag=str(payload["opencc_upstream_tag"]),
            upstream_commit=str(payload["opencc_upstream_commit"]),
        )
        locations.append(location)
    print(f"official OpenCC payload manifest valid ({payload['status']}); payloads={len(locations)}")
    print("verified runtimes: " + ", ".join(sorted(locations)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

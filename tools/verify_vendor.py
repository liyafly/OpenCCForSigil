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


def _validate_payload(record: Mapping[str, object], data_files: Mapping[str, str]) -> tuple[str, str]:
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
    root = _payload_root(payload_path)
    if not root.is_dir():
        raise SystemExit(f"vendored payload is missing: {root}")
    actual_payload_hash = _sha256_tree(root)
    if actual_payload_hash.lower() != str(record["payload_sha256"]).lower():
        raise SystemExit(
            f"payload SHA-256 mismatch for {payload_path}: expected {record['payload_sha256']}, got {actual_payload_hash}"
        )
    actual_data_files = _data_manifest(root)
    if actual_data_files != data_files:
        raise SystemExit(f"payload data/config files differ from the manifest: {payload_path}")
    for config, digest in record["config_hashes"].items():
        if not isinstance(config, str) or not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise SystemExit(f"invalid config hash for {config!r}")
        data_path = f"opencc/clib/share/opencc/{config}.json"
        if data_files.get(data_path) != digest:
            raise SystemExit(f"config hash does not match vendored data for {config!r}")
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
    if not isinstance(payload["config_data"], dict):
        raise SystemExit("manifest config_data must be an object")
    data_files = payload["config_data"].get("files")
    data_manifest_sha256 = payload["config_data"].get("manifest_sha256")
    if not isinstance(data_files, dict) or not data_files:
        raise SystemExit("manifest config_data.files must contain vendored data hashes")
    if not isinstance(data_manifest_sha256, str) or not HEX64.fullmatch(data_manifest_sha256):
        raise SystemExit("manifest config_data.manifest_sha256 is missing or malformed")
    if _canonical_manifest_hash(data_files) != data_manifest_sha256:
        raise SystemExit("manifest config_data.manifest_sha256 does not match config_data.files")

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
        _, location = _validate_payload(record, data_files)
        locations.append(location)
    print(f"official OpenCC payload manifest valid ({payload['status']}); payloads={len(locations)}")
    print("verified runtimes: " + ", ".join(sorted(locations)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

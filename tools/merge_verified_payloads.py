#!/usr/bin/env python3
"""Merge target-runner payload artifacts into one verified Fat Plugin vendor tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Iterable, Mapping
import uuid


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "opencc"
MANIFEST_PATH = VENDOR_ROOT / "manifest.json"


def _files(root: Path) -> Iterable[Path]:
    return (path for path in root.rglob("*") if path.is_file())


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


def _identity(record: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(
        record.get(key)
        for key in ("python_implementation", "python_version", "python_abi", "os", "architecture")
    )


def _payload_id(record: Mapping[str, object]) -> str:
    return f"{record['os']}-{record['architecture']}-{record['python_abi']}"


def _copy_payload(source: Path, destination: Path) -> None:
    if destination.exists():
        if _sha256_tree(destination) != _sha256_tree(source):
            backup = destination.with_name(f".{destination.name}.previous-{uuid.uuid4().hex}")
            destination.rename(backup)
            try:
                _copy_payload(source, destination)
            except Exception:
                if destination.exists():
                    shutil.rmtree(destination)
                backup.rename(destination)
                raise
            shutil.rmtree(backup)
        return
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        staging.rmdir()
        shutil.copytree(source, staging, copy_function=shutil.copy2)
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def merge(artifact_root: Path, vendor_root: Path = VENDOR_ROOT) -> int:
    manifest_path = vendor_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exports = sorted(artifact_root.rglob("record.json"))
    if not exports:
        raise SystemExit(f"no verified payload artifacts found under {artifact_root}")

    records: dict[tuple[object, ...], dict[str, object]] = {}
    for record in manifest.get("payloads", []):
        records[_identity(record)] = dict(record)
    reference_config_data = manifest.get("config_data")

    for export_path in exports:
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        if exported.get("schema_version") != 1:
            raise SystemExit(f"unsupported payload artifact schema: {export_path}")
        record = exported.get("record")
        if not isinstance(record, dict):
            raise SystemExit(f"payload artifact record is malformed: {export_path}")
        if record.get("payload_runtime_test") != "passed":
            raise SystemExit(f"payload artifact was not target-runtime tested: {export_path}")
        payload_source = export_path.parent / "payload"
        if not payload_source.is_dir():
            raise SystemExit(f"payload directory is missing beside record: {export_path}")
        actual_hash = _sha256_tree(payload_source)
        if actual_hash != record.get("payload_sha256"):
            raise SystemExit(
                f"payload artifact hash mismatch for {export_path}: expected {record.get('payload_sha256')}, got {actual_hash}"
            )
        if exported.get("opencc_version") != manifest.get("opencc_version"):
            raise SystemExit(f"OpenCC version mismatch in payload artifact: {export_path}")
        if exported.get("opencc_upstream_tag") != manifest.get("opencc_upstream_tag"):
            raise SystemExit(f"OpenCC upstream tag mismatch in payload artifact: {export_path}")
        if exported.get("opencc_upstream_commit") != manifest.get("opencc_upstream_commit"):
            raise SystemExit(f"OpenCC upstream commit mismatch in payload artifact: {export_path}")
        config_data = exported.get("config_data")
        if config_data != reference_config_data:
            raise SystemExit(f"config/data provenance mismatch in payload artifact: {export_path}")

        payload_id = _payload_id(record)
        expected_path = f"payloads/{payload_id}"
        if record.get("payload_path") != expected_path:
            raise SystemExit(f"payload path does not match runtime identity: {export_path}")
        destination = vendor_root / expected_path
        _copy_payload(payload_source, destination)
        records[_identity(record)] = dict(record)

    for payload_root in sorted((vendor_root / "payloads").glob("*/opencc/clib/bin")):
        for executable in payload_root.iterdir():
            if executable.is_file():
                executable.chmod(executable.stat().st_mode | 0o111)

    manifest["status"] = "phase1-fat-payloads-verified"
    manifest["payloads"] = sorted(
        records.values(), key=lambda item: (str(item["os"]), str(item["architecture"]), str(item["python_abi"]))
    )
    temporary = manifest_path.with_name(f".{manifest_path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    print(f"merged {len(exports)} verified runner payload artifacts")
    print("payloads: " + ", ".join(str(item["payload_path"]) for item in manifest["payloads"]))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--vendor-root", type=Path, default=VENDOR_ROOT)
    args = parser.parse_args()
    return merge(args.artifact_root, args.vendor_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

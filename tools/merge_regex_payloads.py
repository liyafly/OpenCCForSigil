#!/usr/bin/env python3
"""Merge per-runtime tested regex artifacts into the plugin vendor tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import uuid

try:
    from regex_payload import (
        LOCK_PATH, load_lock, payload_id, sha256_file, sha256_tree,
    )
    from runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES, format_runtime_identity
    from native_compatibility import NativeCompatibilityError, validate_binary_path
except ModuleNotFoundError:  # Imported as tools.merge_regex_payloads by tests.
    from tools.regex_payload import (
        LOCK_PATH, load_lock, payload_id, sha256_file, sha256_tree,
    )
    from tools.runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES, format_runtime_identity
    from tools.native_compatibility import NativeCompatibilityError, validate_binary_path


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "regex"
MANIFEST_PATH = VENDOR_ROOT / "manifest.json"
IDENTITY_KEYS = (
    "python_implementation", "python_version", "python_abi", "os", "architecture"
)


def _identity(record):
    return tuple(record.get(key) for key in IDENTITY_KEYS)


def _wheel_by_identity(lock):
    return {
        tuple(record[key] for key in IDENTITY_KEYS): record
        for record in lock["wheels"]
    }


def _validate_record(export_record, payload_root: Path, wheel_records: dict) -> tuple:
    if export_record.get("schema_version") != 1 or export_record.get("package") != "regex":
        raise SystemExit(f"unsupported regex payload artifact: {payload_root.parent}")
    identity = _identity(export_record)
    wheel = wheel_records.get(identity)
    if wheel is None:
        raise SystemExit("unexpected regex runtime identity: " + format_runtime_identity(identity))
    for record_key, lock_key in (
        ("version", "version"), ("wheel_filename", "filename"),
        ("wheel_url", "url"), ("wheel_sha256", "sha256"),
    ):
        expected = ("2026.9.10" if lock_key == "version" else wheel[lock_key])
        if export_record.get(record_key) != expected:
            raise SystemExit(f"regex artifact does not match wheel lock: {record_key}")
    expected_payload = "payloads/" + payload_id(identity)
    if export_record.get("payload_path") != expected_payload:
        raise SystemExit(f"regex payload path does not match runtime identity: {payload_root.parent}")
    if not payload_root.is_dir():
        raise SystemExit(f"regex payload artifact is missing: {payload_root}")
    actual_hash = sha256_tree(payload_root)
    if actual_hash != export_record.get("payload_sha256"):
        raise SystemExit(f"regex payload hash mismatch: {payload_root}")
    file_hashes = export_record.get("files")
    if not isinstance(file_hashes, dict) or not file_hashes:
        raise SystemExit(f"regex artifact file hashes are missing: {payload_root}")
    actual_files = {
        path.relative_to(payload_root).as_posix(): sha256_file(path)
        for path in sorted(payload_root.rglob("*"))
        if path.is_file() and path.suffix not in {".pyc", ".pyo"}
        and "__pycache__" not in path.parts
    }
    if actual_files != file_hashes:
        raise SystemExit(f"regex payload file list or hash mismatch: {payload_root}")
    extension_paths = [path for path in actual_files
                       if path.startswith("regex/_regex.") and path.rsplit(".", 1)[-1] in {"so", "pyd"}]
    if len(extension_paths) != 1:
        raise SystemExit(f"regex payload must contain one native extension: {payload_root}")
    try:
        validate_binary_path(
            payload_root / extension_paths[0],
            runtime_os=str(identity[3]),
            architecture=str(identity[4]),
            require_glibcxx=identity[3] != "linux",
        )
    except NativeCompatibilityError as exc:
        raise SystemExit(f"regex native compatibility failed: {exc}") from exc
    return identity


def _copy_payload(source: Path, destination: Path) -> None:
    if destination.exists():
        if sha256_tree(source) == sha256_tree(destination):
            return
        backup = destination.with_name(f".{destination.name}.previous-{uuid.uuid4().hex}")
        destination.rename(backup)
        try:
            shutil.copytree(source, destination, copy_function=shutil.copy2)
        except Exception:
            if destination.exists():
                shutil.rmtree(destination)
            backup.rename(destination)
            raise
        shutil.rmtree(backup)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        staging.rmdir()
        shutil.copytree(source, staging, copy_function=shutil.copy2)
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def merge(artifact_root: Path, vendor_root: Path = VENDOR_ROOT, *, require_runtimes=False) -> int:
    lock = load_lock()
    wheel_records = _wheel_by_identity(lock)
    existing_records = {}
    existing_manifest = vendor_root / "manifest.json"
    if existing_manifest.is_file() and not require_runtimes:
        old = json.loads(existing_manifest.read_text(encoding="utf-8"))
        if old.get("version") != lock["version"]:
            raise SystemExit("existing regex manifest has a different version")
        existing_records.update({
            _identity(record): dict(record)
            for record in old.get("payloads", []) if isinstance(record, dict)
        })

    artifact_records = {}
    for record_path in sorted(artifact_root.rglob("record.json")):
        export_record = json.loads(record_path.read_text(encoding="utf-8"))
        if export_record.get("package") != "regex":
            continue
        identity = _validate_record(export_record, record_path.parent / "payload", wheel_records)
        if identity in artifact_records:
            raise SystemExit("duplicate regex artifact runtime: " + format_runtime_identity(identity))
        artifact_records[identity] = dict(export_record)

    if not artifact_records:
        raise SystemExit(f"no regex runtime artifacts found under {artifact_root}")
    for identity, record in artifact_records.items():
        source = next(
            path.parent / "payload"
            for path in artifact_root.rglob("record.json")
            if json.loads(path.read_text(encoding="utf-8")).get("package") == "regex"
            and _identity(json.loads(path.read_text(encoding="utf-8"))) == identity
        )
        destination = vendor_root / record["payload_path"]
        _copy_payload(source, destination)
        existing_records[identity] = record

    if require_runtimes:
        expected = set(SUPPORTED_RUNTIME_IDENTITIES)
        actual = set(existing_records)
        missing = expected - actual
        unexpected = actual - expected
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing=" + ",".join(
                    format_runtime_identity(item) for item in sorted(missing, key=str)))
            if unexpected:
                details.append("unexpected=" + ",".join(
                    format_runtime_identity(item) for item in sorted(unexpected, key=str)))
            raise SystemExit("regex runtime matrix mismatch: " + "; ".join(details))

    manifest = {
        "schema_version": 1,
        "package": lock["package"],
        "version": lock["version"],
        "source": lock["source"],
        "wheel_lock_sha256": sha256_file(LOCK_PATH),
        "payloads": sorted(
            existing_records.values(),
            key=lambda item: (str(item["os"]), str(item["architecture"]), str(item["python_abi"])),
        ),
    }
    vendor_root.mkdir(parents=True, exist_ok=True)
    temporary = existing_manifest.with_name(f".{existing_manifest.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(existing_manifest)
    print(f"merged {len(artifact_records)} verified regex runtime artifacts")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--vendor-root", type=Path, default=VENDOR_ROOT)
    parser.add_argument("--require-runtimes", action="store_true")
    args = parser.parse_args()
    return merge(args.artifact_root, args.vendor_root, require_runtimes=args.require_runtimes)


if __name__ == "__main__":
    raise SystemExit(main())

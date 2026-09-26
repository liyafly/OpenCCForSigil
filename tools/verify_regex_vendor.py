#!/usr/bin/env python3
"""Verify the bundled regex payload manifest and package subset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile

try:
    from merge_regex_payloads import _validate_record, _wheel_by_identity
    from regex_payload import LOCK_PATH, load_lock, sha256_file
    from runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES, format_runtime_identity
except ModuleNotFoundError:  # Imported as tools.verify_regex_vendor by tests.
    from tools.merge_regex_payloads import _validate_record, _wheel_by_identity
    from tools.regex_payload import LOCK_PATH, load_lock, sha256_file
    from tools.runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES, format_runtime_identity


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "regex"
MANIFEST_PATH = VENDOR_ROOT / "manifest.json"
IDENTITY_KEYS = (
    "python_implementation", "python_version", "python_abi", "os", "architecture"
)


def _identity(record):
    return tuple(record.get(key) for key in IDENTITY_KEYS)


def _payload_path(vendor_root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if (not value.startswith("payloads/") or relative.is_absolute()
            or ".." in relative.parts or "\\" in value):
        raise SystemExit(f"unsafe regex payload path: {value!r}")
    root = (vendor_root / relative).resolve()
    if vendor_root.resolve() not in root.parents:
        raise SystemExit(f"regex payload escapes vendor tree: {value!r}")
    return root


def validate_manifest(
    vendor_root: Path = VENDOR_ROOT,
    *,
    require_runtimes: bool = False,
) -> tuple[dict, ...]:
    manifest_path = vendor_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read regex vendor manifest: {exc}") from exc
    lock = load_lock()
    if (manifest.get("schema_version"), manifest.get("package"), manifest.get("version"),
            manifest.get("source")) != (
            1, lock["package"], lock["version"], lock["source"]):
        raise SystemExit("regex vendor manifest identity does not match the locked package")
    if manifest.get("wheel_lock_sha256") != sha256_file(LOCK_PATH):
        raise SystemExit("regex vendor manifest was built from a different wheel lock")
    records = manifest.get("payloads")
    if not isinstance(records, list) or not records:
        raise SystemExit("regex vendor manifest must contain payload records")
    wheel_records = _wheel_by_identity(lock)
    identities = set()
    checked = []
    for record in records:
        if not isinstance(record, dict):
            raise SystemExit("regex payload record must be an object")
        identity = _identity(record)
        if identity in identities:
            raise SystemExit("duplicate regex runtime payload: " + format_runtime_identity(identity))
        identities.add(identity)
        payload_root = _payload_path(vendor_root, str(record.get("payload_path", "")))
        try:
            _validate_record(record, payload_root, wheel_records)
        except SystemExit:
            raise
        checked.append(record)
    if require_runtimes:
        expected = set(SUPPORTED_RUNTIME_IDENTITIES)
        missing, unexpected = expected - identities, identities - expected
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing=" + ",".join(
                    format_runtime_identity(item) for item in sorted(missing, key=str)))
            if unexpected:
                details.append("unexpected=" + ",".join(
                    format_runtime_identity(item) for item in sorted(unexpected, key=str)))
            raise SystemExit("regex runtime matrix mismatch: " + "; ".join(details))
    return tuple(checked)


def prepare_package(
    package_root: Path,
    *,
    runtime_identities: set[tuple],
) -> None:
    vendor_root = package_root / "vendor" / "regex"
    manifest_path = vendor_root / "manifest.json"
    records = validate_manifest(vendor_root)
    selected = [record for record in records if _identity(record) in runtime_identities]
    if len(selected) != len(runtime_identities):
        wanted = ", ".join(format_runtime_identity(item) for item in sorted(runtime_identities, key=str))
        raise SystemExit(f"regex manifest does not contain each selected runtime: {wanted}")
    selected_paths = {record["payload_path"] for record in selected}
    for record in records:
        if record["payload_path"] not in selected_paths:
            shutil.rmtree(_payload_path(vendor_root, record["payload_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["payloads"] = selected
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_archive(archive, *, expected_runtime_identities: set[tuple]) -> tuple[dict, ...]:
    """Validate the regex subset embedded in a plugin ZIP without trusting paths."""

    prefix = "OpenCCForSigil/vendor/regex/"
    names = set(archive.namelist())
    manifest_member = prefix + "manifest.json"
    if manifest_member not in names:
        raise SystemExit("plugin artifact is missing vendor/regex/manifest.json")
    with tempfile.TemporaryDirectory(prefix="opencc-regex-artifact-") as temporary:
        vendor_root = Path(temporary) / "regex"
        vendor_root.mkdir(parents=True)
        for name in sorted(item for item in names if item.startswith(prefix)):
            relative = PurePosixPath(name[len(prefix):])
            if (not relative.parts or relative.is_absolute() or ".." in relative.parts
                    or "\\" in name):
                raise SystemExit(f"unsafe regex artifact member: {name!r}")
            if name.endswith("/"):
                raise SystemExit(f"regex artifact contains explicit directory entry: {name}")
            destination = vendor_root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
        records = validate_manifest(vendor_root)
        identities = {_identity(record) for record in records}
        if identities != expected_runtime_identities:
            raise SystemExit("regex payload runtimes differ from OpenCC package runtimes")
        expected_members = {manifest_member}
        for record in records:
            payload_path = PurePosixPath(str(record["payload_path"]))
            expected_members.update(
                prefix + payload_path.as_posix() + "/" + relative
                for relative in record["files"]
            )
        actual_members = {name for name in names if name.startswith(prefix)}
        if actual_members != expected_members:
            extras = sorted(actual_members - expected_members)
            missing = sorted(expected_members - actual_members)
            details = []
            if extras:
                details.append("unmanifested=" + ", ".join(extras[:5]))
            if missing:
                details.append("missing=" + ", ".join(missing[:5]))
            raise SystemExit("regex artifact file set mismatch: " + "; ".join(details))
        return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-root", type=Path, default=VENDOR_ROOT)
    parser.add_argument("--require-runtimes", action="store_true")
    args = parser.parse_args()
    records = validate_manifest(args.vendor_root, require_runtimes=args.require_runtimes)
    print(f"regex vendor manifest valid ({len(records)} payloads, {records[0]['version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

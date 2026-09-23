#!/usr/bin/env python3
"""Build or validate the complete versioned release asset set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

try:
    from package_contract import package_asset_name, package_oslist, package_runtime_ids
    from runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES
except ModuleNotFoundError:  # Imported as tools.release_assets by tests.
    from tools.package_contract import package_asset_name, package_oslist, package_runtime_ids
    from tools.runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES


FAT_ASSET_PREFIX = "OpenCCForSigil_"
CHECKSUMS_NAME = "SHA256SUMS.txt"
PLATFORM_RUNTIME_IDS = tuple(sorted(
    f"{identity[3]}-{identity[4]}-{identity[2]}"
    for identity in SUPPORTED_RUNTIME_IDENTITIES
))


def expected_zip_names(version: str) -> dict[str, str]:
    names = {runtime: package_asset_name(version, "platform", runtime)
             for runtime in PLATFORM_RUNTIME_IDS}
    names["fat"] = package_asset_name(version, "fat")
    return names


def validate_plugin_zip_version(archive_path: Path, expected_version: str) -> str:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            plugin_xml = archive.read("OpenCCForSigil/plugin.xml")
        actual = ET.fromstring(plugin_xml).findtext("version")
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise SystemExit(f"{archive_path.name}: cannot read plugin.xml version: {exc}") from exc
    if actual != expected_version:
        raise SystemExit(
            f"{archive_path.name}: plugin.xml version {actual!r} does not match "
            f"release version {expected_version!r}"
        )
    return actual


def _validate_zip_contract(
    archive_path: Path,
    *,
    version: str,
    flavor: str,
    runtime: str | None,
) -> str:
    validate_plugin_zip_version(archive_path, version)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise SystemExit(f"{archive_path.name}: archive contains duplicate member names")
            if not names or any(not name.startswith("OpenCCForSigil/") for name in names):
                raise SystemExit(
                    f"{archive_path.name}: archive must contain only OpenCCForSigil/"
                )
            manifest = json.loads(
                archive.read("OpenCCForSigil/vendor/opencc/manifest.json")
            )
            plugin_xml = ET.fromstring(archive.read("OpenCCForSigil/plugin.xml"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise SystemExit(f"{archive_path.name}: cannot read package contract: {exc}") from exc

    if not isinstance(manifest, dict):
        raise SystemExit(f"{archive_path.name}: vendor manifest must be an object")
    package = manifest.get("package")
    if not isinstance(package, dict) or package.get("flavor") != flavor:
        raise SystemExit(f"{archive_path.name}: package flavor must be {flavor!r}")
    payloads = manifest.get("payloads")
    if not isinstance(payloads, list) or not payloads or not all(
        isinstance(payload, dict) for payload in payloads
    ):
        raise SystemExit(f"{archive_path.name}: manifest has no valid payload records")
    records = [payload for payload in payloads if isinstance(payload, dict)]
    try:
        runtimes = package_runtime_ids(records)
        expected_oslist = package_oslist(records)
    except ValueError as exc:
        raise SystemExit(f"{archive_path.name}: invalid payload records: {exc}") from exc
    if len(runtimes) != len(set(runtimes)) or package.get("runtimes") != runtimes:
        raise SystemExit(f"{archive_path.name}: package runtimes differ from payload records")

    if flavor == "fat":
        expected_runtimes = list(PLATFORM_RUNTIME_IDS)
        expected_asset = package_asset_name(version, "fat")
    else:
        if runtime is None:
            raise SystemExit("platform release asset is missing its runtime identity")
        expected_runtimes = [runtime]
        expected_asset = package_asset_name(version, "platform", runtime)
    if runtimes != expected_runtimes:
        raise SystemExit(
            f"{archive_path.name}: expected runtimes {expected_runtimes}, got {runtimes}"
        )
    if archive_path.name != expected_asset or package.get("asset_name") != expected_asset:
        raise SystemExit(
            f"{archive_path.name}: asset name must match package contract {expected_asset!r}"
        )
    if plugin_xml.findtext("oslist") != expected_oslist:
        raise SystemExit(
            f"{archive_path.name}: plugin.xml oslist must be {expected_oslist!r}"
        )
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def _validate_zip_assets(asset_dir: Path, version: str) -> dict[str, str]:
    names = expected_zip_names(version)
    checksums: dict[str, str] = {}
    for runtime, name in names.items():
        is_fat = runtime == "fat"
        path = asset_dir / name
        if not path.is_file():
            raise SystemExit(f"release asset is missing: {path}")
        checksums[name] = _validate_zip_contract(
            path,
            version=version,
            flavor="fat" if is_fat else "platform",
            runtime=None if is_fat else runtime,
        )
    return checksums


def write_checksums(asset_dir: Path, version: str) -> Path:
    asset_dir = asset_dir.resolve()
    checksums = _validate_zip_assets(asset_dir, version)
    contents = "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums))
    output = asset_dir / CHECKSUMS_NAME
    output.write_text(contents, encoding="ascii", newline="\n")
    return output


def validate_release_assets(asset_dir: Path, version: str) -> None:
    asset_dir = asset_dir.resolve()
    checksums = _validate_zip_assets(asset_dir, version)
    expected_files = set(checksums) | {CHECKSUMS_NAME}
    actual_paths = list(asset_dir.iterdir())
    actual_files = {path.name for path in actual_paths if path.is_file()}
    if actual_files != expected_files or len(actual_paths) != len(expected_files):
        raise SystemExit(
            "release asset directory must contain exactly the six plugin ZIPs and "
            f"{CHECKSUMS_NAME}; found {sorted(path.name for path in actual_paths)}"
        )

    sums_path = asset_dir / CHECKSUMS_NAME
    try:
        lines = sums_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"cannot read {CHECKSUMS_NAME}: {exc}") from exc
    parsed: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\s]+)", line)
        if not match or match.group(2) in parsed:
            raise SystemExit(f"invalid or duplicate checksum line: {line!r}")
        parsed[match.group(2)] = match.group(1)
    if parsed != checksums:
        raise SystemExit(f"{CHECKSUMS_NAME} does not match the six release ZIPs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    if args.write_checksums:
        write_checksums(args.asset_dir, args.version)
    validate_release_assets(args.asset_dir, args.version)
    print(f"validated seven release assets for OpenCCForSigil {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

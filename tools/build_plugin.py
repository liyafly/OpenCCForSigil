#!/usr/bin/env python3
"""Validate and package the Sigil plugin after Build/Release payload checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET

try:
    from verify_vendor import validate_manifest
    from validate_artifact import validate as validate_artifact
    from runtime_subset import RuntimeSubsetError, derive_record, sha256_tree, validate_derivation
except ModuleNotFoundError:  # Imported as tools.build_plugin by tests.
    from tools.verify_vendor import validate_manifest
    from tools.validate_artifact import validate as validate_artifact
    from tools.runtime_subset import RuntimeSubsetError, derive_record, sha256_tree, validate_derivation


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugin" / "OpenCCForSigil"
PLUGIN_XML = PLUGIN_DIR / "plugin.xml"
VERSION_FILE = PLUGIN_DIR / "app" / "version.py"
MANIFEST_FILE = PLUGIN_DIR / "vendor" / "opencc" / "manifest.json"


def _read_plugin_version() -> str:
    source = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'^PLUGIN_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    if not match:
        raise SystemExit("PLUGIN_VERSION is missing from app/version.py")
    return match.group(1)


def validate(*, require_runtimes: bool = False) -> str:
    if not PLUGIN_XML.is_file():
        raise SystemExit(f"missing plugin metadata: {PLUGIN_XML}")
    if not (PLUGIN_DIR / "plugin.py").is_file():
        raise SystemExit("missing plugin.py")
    if not MANIFEST_FILE.is_file():
        raise SystemExit("missing vendor/opencc/manifest.json")
    validate_manifest(require_runtimes=require_runtimes)

    root = ET.parse(PLUGIN_XML).getroot()
    if root.tag != "plugin":
        raise SystemExit("plugin.xml root must be <plugin>")
    name = root.findtext("name")
    version = root.findtext("version")
    if name != "OpenCCForSigil":
        raise SystemExit("plugin.xml <name> must be OpenCCForSigil")
    code_version = _read_plugin_version()
    if version != code_version:
        raise SystemExit(f"plugin.xml version {version!r} != code version {code_version!r}")

    if root.findtext("type") != "edit":
        raise SystemExit("plugin.xml <type> must be edit")
    return code_version


def _iter_package_files(package_root: Path = PLUGIN_DIR):
    ignored_names = {".DS_Store"}
    for path in sorted(package_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in ignored_names or path.suffix in {".pyc", ".pyo"}:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def _zip_mode(path: Path) -> int:
    return 0o755 if path.stat().st_mode & 0o111 else 0o644


def _prepare_runtime_subsets(package_root: Path) -> None:
    manifest_path = package_root / "vendor" / "opencc" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vendor_root = manifest_path.parent
    payloads = manifest.get("payloads")
    if not isinstance(payloads, list) or not payloads:
        raise SystemExit("vendor manifest must contain payload records")
    for record in payloads:
        if not isinstance(record, dict):
            raise SystemExit("vendor manifest payload records must be objects")
        payload_path = Path(str(record.get("payload_path", "")))
        if payload_path.is_absolute() or ".." in payload_path.parts:
            raise SystemExit(f"unsafe manifest payload path: {payload_path}")
        source = vendor_root / payload_path
        native = record.get("native_plugins")
        jieba = native.get("opencc-jieba") if isinstance(native, dict) else None
        if not isinstance(jieba, dict):
            raise SystemExit(f"official native opencc-jieba record is missing: {payload_path}")
        plugin_dir = str(jieba.get("plugin_dir", ""))
        library_path = str(jieba.get("library_path", ""))
        if "derivation" in record or "record_describes" in record:
            try:
                validate_derivation(
                    record,
                    kept_paths=(path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()),
                    plugin_dir=plugin_dir,
                    library_path=library_path,
                )
            except RuntimeSubsetError as exc:
                raise SystemExit(f"runtime subset is invalid for {payload_path}: {exc}") from exc
            if sha256_tree(source).lower() != str(record.get("payload_sha256", "")).lower():
                raise SystemExit(f"runtime subset payload hash mismatch: {payload_path}")
            continue
        temporary_subset = source.with_name(source.name + ".runtime-subset")
        try:
            derived, _ = derive_record(record, source, temporary_subset)
        except RuntimeSubsetError as exc:
            raise SystemExit(f"cannot derive runtime subset for {payload_path}: {exc}") from exc
        shutil.rmtree(source)
        temporary_subset.rename(source)
        record.clear()
        record.update(derived)

    config_data = manifest.get("config_data")
    if isinstance(config_data, dict):
        config_payloads = config_data.get("payloads")
        if isinstance(config_payloads, dict):
            config_data["payloads"] = {
                str(record["payload_path"]): record["config_data"]
                for record in payloads
                if isinstance(record, dict) and isinstance(record.get("config_data"), dict)
            }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(output: Path, *, require_runtimes: bool = False) -> Path:
    version = validate(require_runtimes=require_runtimes)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with tempfile.TemporaryDirectory(prefix="opencc-plugin-build-", dir=output.parent) as temporary:
        package_root = Path(temporary) / "OpenCCForSigil"
        shutil.copytree(PLUGIN_DIR, package_root, copy_function=shutil.copy2)
        _prepare_runtime_subsets(package_root)
        with zipfile.ZipFile(
            output,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for path in _iter_package_files(package_root):
                relative = path.relative_to(package_root)
                name = (Path("OpenCCForSigil") / relative).as_posix()
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = _zip_mode(path) << 16
                info.create_system = 3
                archive.writestr(info, path.read_bytes())
    validate_artifact(output, require_runtimes=require_runtimes)
    print(f"created {output} ({version})")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without creating a ZIP")
    parser.add_argument(
        "--require-runtimes",
        action="store_true",
        help="require every supported Fat Plugin runtime identity",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output ZIP path (defaults to dist/OpenCCForSigil_<plugin version>.zip)",
    )
    args = parser.parse_args()
    version = validate(require_runtimes=args.require_runtimes)
    if args.check:
        print(f"plugin metadata valid ({version})")
        return 0
    output = args.output or ROOT / "dist" / f"OpenCCForSigil_{version}.zip"
    build(output, require_runtimes=args.require_runtimes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

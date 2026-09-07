#!/usr/bin/env python3
"""Validate and package the Sigil plugin after Build/Release payload checks."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

try:
    from verify_vendor import validate_manifest
    from validate_artifact import validate as validate_artifact
except ModuleNotFoundError:  # Imported as tools.build_plugin by tests.
    from tools.verify_vendor import validate_manifest
    from tools.validate_artifact import validate as validate_artifact


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


def _iter_package_files():
    ignored_names = {".DS_Store"}
    for path in sorted(PLUGIN_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.name in ignored_names or path.suffix in {".pyc", ".pyo"}:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def _zip_mode(path: Path) -> int:
    return 0o755 if path.stat().st_mode & 0o111 else 0o644


def build(output: Path, *, require_runtimes: bool = False) -> Path:
    version = validate(require_runtimes=require_runtimes)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in _iter_package_files():
            relative = path.relative_to(PLUGIN_DIR)
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

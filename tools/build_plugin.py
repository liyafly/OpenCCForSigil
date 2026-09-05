#!/usr/bin/env python3
"""Validate and package the Sigil plugin.

Phase 0 packages source and the manifest skeleton only. Native artifact
collection is deliberately a separate Phase 1 build step.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


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


def validate() -> str:
    if not PLUGIN_XML.is_file():
        raise SystemExit(f"missing plugin metadata: {PLUGIN_XML}")
    if not (PLUGIN_DIR / "plugin.py").is_file():
        raise SystemExit("missing plugin.py")
    if not MANIFEST_FILE.is_file():
        raise SystemExit("missing vendor/opencc/manifest.json")

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


def build(output: Path) -> Path:
    version = validate()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_package_files():
            relative = path.relative_to(PLUGIN_DIR)
            archive.write(path, Path("OpenCCForSigil") / relative)
    print(f"created {output} ({version})")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without creating a ZIP")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "OpenCCForSigil_0.1.0.zip",
    )
    args = parser.parse_args()
    version = validate()
    if args.check:
        print(f"plugin metadata valid ({version})")
        return 0
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

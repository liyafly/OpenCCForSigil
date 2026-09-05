#!/usr/bin/env python3
"""Build the versioned normative specification bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC_VERSION = "1.4"
SPEC_DIR = ROOT / "docs" / f"OpenCCForSigil_Spec_v{SPEC_VERSION}"
FILES = {
    "OpenCCForSigil_Engineering_Spec.md": "OpenCCForSigil_Engineering_Spec.md",
    "INVARIANTS.md": "INVARIANTS.md",
    "REVISION_NOTES.md": "REVISION_NOTES.md",
}


def build(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    versioned_files = []
    for source_name, archive_name in FILES.items():
        source = SPEC_DIR / source_name
        if not source.is_file():
            raise SystemExit(f"missing specification source: {source}")
        versioned_name = archive_name.removesuffix(".md") + f"_v{SPEC_VERSION}.md"
        target = output_dir / versioned_name
        target.write_bytes(source.read_bytes())
        versioned_files.append((target, versioned_name))

    bundle = output_dir / f"OpenCCForSigil_Spec_v{SPEC_VERSION}_bundle.zip"
    if bundle.exists():
        bundle.unlink()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        root = f"OpenCCForSigil_Spec_v{SPEC_VERSION}"
        for source_name, archive_name in FILES.items():
            archive.write(SPEC_DIR / source_name, f"{root}/{archive_name}")
    print(f"created {bundle}")
    for target, _ in versioned_files:
        print(f"created {target}")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="directory for versioned copies and the bundle",
    )
    args = parser.parse_args()
    build(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

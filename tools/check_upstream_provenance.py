#!/usr/bin/env python3
"""Check the pinned OpenCC provenance used by the CI payload cache."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "native_build" / "payload-lock.json"
MANIFEST_PATH = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "opencc" / "manifest.json"
_PROVENANCE_FIELDS = ("opencc_version", "opencc_upstream_tag", "opencc_upstream_commit")


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read provenance file: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"provenance file must contain a JSON object: {path}")
    return value


def check(lock_path: Path = LOCK_PATH, manifest_path: Path = MANIFEST_PATH) -> str:
    lock = _load(lock_path)
    manifest = _load(manifest_path)
    if lock.get("schema_version") != 1:
        raise SystemExit(f"unsupported payload lock schema: {lock_path}")
    missing = [
        field
        for field in _PROVENANCE_FIELDS
        if not isinstance(lock.get(field), str) or not str(lock[field]).strip()
    ]
    if missing:
        raise SystemExit("payload lock missing provenance: " + ", ".join(missing))
    mismatched = [
        field for field in _PROVENANCE_FIELDS if lock.get(field) != manifest.get(field)
    ]
    if mismatched:
        raise SystemExit(
            "OpenCC provenance differs between payload lock and vendor manifest: "
            + ", ".join(mismatched)
        )
    commit = str(lock["opencc_upstream_commit"])
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            handle.write(f"commit={commit}\n")
    return commit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()
    commit = check(args.lock, args.manifest)
    print(f"OpenCC upstream provenance is consistent: {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate the Phase 0 official wheel manifest shape without importing it."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "opencc" / "manifest.json"


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
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
    if not isinstance(payload["payloads"], list):
        raise SystemExit("manifest payloads must be a list")
    expected_policy = {
        "implementation": "CPython",
        "major": 3,
        "minor": 14,
        "abi": "cp314",
        "production_baseline": "3.14.2",
        "development_ci": "3.14.7",
        "patch_participates_in_payload_selection": False,
    }
    if payload["python_compatibility"] != expected_policy:
        raise SystemExit("manifest Python compatibility policy is not CPython 3.14.x/cp314")
    print(f"official OpenCC payload manifest valid ({payload['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

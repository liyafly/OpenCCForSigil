#!/usr/bin/env python3
"""Export the current runner's verified OpenCC payload for CI artifact upload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugin" / "OpenCCForSigil"
MANIFEST_PATH = PLUGIN_ROOT / "vendor" / "opencc" / "manifest.json"
sys.path.insert(0, str(PLUGIN_ROOT))

from opencc_backend.runtime_selector import RuntimeSelector  # noqa: E402
from runtime_subset import derive_record  # noqa: E402


def _identity(record: dict[str, object]) -> tuple[object, ...]:
    return tuple(
        record.get(key)
        for key in ("python_implementation", "python_version", "python_abi", "os", "architecture")
    )


def export(output: Path, *, full_output: Path | None = None) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    runtime, selected, payload_root = RuntimeSelector().select()
    identity = (
        runtime.python_implementation,
        runtime.compatibility_version,
        runtime.python_abi,
        runtime.os,
        runtime.architecture,
    )
    records = [record for record in manifest.get("payloads", []) if _identity(record) == identity]
    if len(records) != 1:
        raise SystemExit(f"manifest does not contain exactly one current-runner payload: {identity}")
    record = dict(records[0])
    if record.get("payload_runtime_test") != "passed":
        raise SystemExit(f"current payload has not passed target self-test: {record.get('payload_path')}")
    if record.get("payload_path") != f"payloads/{selected.runtime.payload_id}":
        raise SystemExit("selected runtime payload path does not match its runtime identity")

    protected_paths = (PLUGIN_ROOT.resolve(), payload_root.resolve())
    outputs = [("runtime subset output", output)]
    if full_output is not None:
        outputs.append(("full payload cache", full_output))
    resolved_outputs = []
    for label, path in outputs:
        resolved = path.resolve()
        if any(
            protected == resolved
            or protected in resolved.parents
            or resolved in protected.parents
            for protected in protected_paths
        ):
            raise SystemExit(f"{label} must not overlap the plugin source tree")
        resolved_outputs.append((label, resolved))
    if len(resolved_outputs) == 2:
        first = resolved_outputs[0][1]
        second = resolved_outputs[1][1]
        if first == second or first in second.parents or second in first.parents:
            raise SystemExit("full payload cache and runtime subset output must use separate directories")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    full_record = record
    record, subset = derive_record(record, payload_root, output / "payload")
    if full_output is not None:
        if full_output.exists():
            shutil.rmtree(full_output)
        full_output.mkdir(parents=True, exist_ok=True)
        shutil.copytree(payload_root, full_output / "payload", copy_function=shutil.copy2)
        full_export = {
            "schema_version": 1,
            "runtime": {
                "python_implementation": runtime.python_implementation,
                "python_version": runtime.compatibility_version,
                "python_patch": runtime.python_patch,
                "python_abi": runtime.python_abi,
                "os": runtime.os,
                "architecture": runtime.architecture,
            },
            "record": full_record,
            "config_data": full_record.get("config_data", {}),
            "opencc_version": manifest.get("opencc_version"),
            "opencc_upstream_tag": manifest.get("opencc_upstream_tag"),
            "opencc_upstream_commit": manifest.get("opencc_upstream_commit"),
        }
        (full_output / "record.json").write_text(
            json.dumps(full_export, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    exported = {
        "schema_version": 1,
        "runtime": {
            "python_implementation": runtime.python_implementation,
            "python_version": runtime.compatibility_version,
            "python_patch": runtime.python_patch,
            "python_abi": runtime.python_abi,
            "os": runtime.os,
            "architecture": runtime.architecture,
        },
        "record": record,
        "config_data": record.get("config_data", {}),
        "subset": subset,
        "opencc_version": manifest.get("opencc_version"),
        "opencc_upstream_tag": manifest.get("opencc_upstream_tag"),
        "opencc_upstream_commit": manifest.get("opencc_upstream_commit"),
    }
    (output / "record.json").write_text(
        json.dumps(exported, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"exported verified payload {selected.runtime.payload_id} to {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--full-output",
        type=Path,
        help="also cache the complete tested source payload for later full-tree CI checks",
    )
    args = parser.parse_args()
    export(args.output, full_output=args.full_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

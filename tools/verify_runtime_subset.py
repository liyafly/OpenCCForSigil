#!/usr/bin/env python3
"""Smoke-test one exported subset in a clean process and compare it with its full-tree CLI."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugin" / "OpenCCForSigil"
MANIFEST_PATH = PLUGIN_ROOT / "vendor" / "opencc" / "manifest.json"
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(PLUGIN_ROOT))

from opencc_backend.backend import OpenCCBackend  # noqa: E402
from opencc_backend.configs import JIEBA_CONFIGS, V1_CONFIGS  # noqa: E402
from opencc_backend.runtime_selector import RuntimeSelector  # noqa: E402
from differential_test import compare as compare_standard, load_cases as load_standard_cases  # noqa: E402
from differential_jieba_test import compare as compare_jieba, load_cases as load_jieba_cases  # noqa: E402


def _identity(record: dict[str, object]) -> tuple[object, ...]:
    return tuple(
        record.get(key)
        for key in ("python_implementation", "python_version", "python_abi", "os", "architecture")
    )


def _write_manifest_stage(export_root: Path, stage_root: Path) -> tuple[Path, Path, Path]:
    exported = json.loads((export_root / "record.json").read_text(encoding="utf-8"))
    record = exported.get("record")
    runtime = exported.get("runtime")
    if not isinstance(record, dict) or not isinstance(runtime, dict):
        raise SystemExit("runtime subset export record is malformed")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    full_records = [item for item in manifest.get("payloads", []) if _identity(item) == _identity(record)]
    if len(full_records) != 1:
        raise SystemExit("full source manifest does not contain exactly one matching runtime")
    source_root = PLUGIN_ROOT / "vendor" / "opencc" / str(full_records[0]["payload_path"])
    if not source_root.is_dir():
        raise SystemExit(f"full source payload is missing: {source_root}")
    manifest["payloads"] = [record]
    config_data = manifest.get("config_data")
    if not isinstance(config_data, dict):
        raise SystemExit("source vendor config_data is malformed")
    config_data["payloads"] = {str(record["payload_path"]): record["config_data"]}
    vendor_root = stage_root / "vendor" / "opencc"
    payload_root = vendor_root / str(record["payload_path"])
    payload_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(export_root / "payload", payload_root, copy_function=shutil.copy2)
    manifest_path = vendor_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path, payload_root, source_root


def _compressed_size(payload_root: Path) -> int:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(payload_root.rglob("*")):
            if path.is_file():
                archive.writestr(path.relative_to(payload_root).as_posix(), path.read_bytes())
    return buffer.tell()


def verify(export_root: Path) -> int:
    stage_parent = Path(tempfile.mkdtemp(prefix="opencc-subset-smoke-"))
    try:
        manifest_path, payload_root, source_root = _write_manifest_stage(export_root, stage_parent)
        selector = RuntimeSelector(manifest_path=manifest_path)
        _module, _runtime, payload, selected_root, import_origin = selector.import_opencc()
        if selected_root.resolve() != payload_root.resolve():
            raise SystemExit(f"runtime selector chose an unexpected payload: {selected_root}")
        if payload.runtime.payload_id != payload_root.name:
            raise SystemExit(f"runtime selector chose an unexpected identity: {payload.runtime.payload_id}")
        if payload_root.resolve() not in (payload_root / import_origin).resolve().parents:
            raise SystemExit(f"OpenCC import escaped the exported subset: {import_origin}")
        backend = OpenCCBackend("s2t", selector)
        result = backend.self_test(include_optional=True)
        if not result.passed:
            raise SystemExit(f"runtime subset backend self-test failed: {result.error or result.checks}")
        available = set(backend.available_configs())
        expected = set(V1_CONFIGS) | set(JIEBA_CONFIGS)
        if available != expected:
            raise SystemExit(f"runtime subset config list differs: {sorted(available ^ expected)}")
        sample = "汉字、软件、台湾香港与著作权。"
        for config in (*V1_CONFIGS, *JIEBA_CONFIGS):
            output = backend.convert_for_config(config, sample)
            if not isinstance(output, str):
                raise SystemExit(f"runtime subset conversion was not text: {config}")

        cli_name = "opencc.exe" if os.name == "nt" else "opencc"
        cli = source_root / "opencc" / "clib" / "bin" / cli_name
        if not cli.is_file():
            raise SystemExit(f"full-tree OpenCC CLI is missing: {cli}")
        standard_corpus = ROOT / "tests" / "fixtures" / "opencc_smoke.jsonl"
        jieba_corpus = ROOT / "tests" / "fixtures" / "opencc_jieba_smoke.jsonl"
        standard_differences = compare_standard(
            cli, payload_root, load_standard_cases(standard_corpus)
        )
        if standard_differences:
            raise SystemExit(f"runtime subset standard CLI differences: {standard_differences[:3]}")
        jieba_differences = compare_jieba(cli, payload_root, load_jieba_cases(jieba_corpus))
        if jieba_differences:
            raise SystemExit(f"runtime subset Jieba CLI differences: {jieba_differences[:3]}")

        bytecode = [
            path.relative_to(payload_root).as_posix()
            for path in payload_root.rglob("*")
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}
        ]
        if bytecode:
            raise SystemExit("runtime subset smoke created bytecode: " + ", ".join(bytecode[:10]))
        subset_bytes = _compressed_size(payload_root)
        payload_id = payload.runtime.payload_id
        summary = f"| `{payload_id}` | {subset_bytes:,} bytes | {subset_bytes / 1_000_000:.2f} MB |\n"
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with Path(summary_path).open("a", encoding="utf-8") as handle:
                handle.write("\n### Runtime subset size\n\n| Runtime | Compressed size | Decimal MB |\n| --- | ---: | ---: |\n")
                handle.write(summary)
        print(f"runtime subset verified: {payload_id}; {subset_bytes:,} compressed bytes; 23 configs")
        return 0
    finally:
        shutil.rmtree(stage_parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    args = parser.parse_args()
    return verify(args.export_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

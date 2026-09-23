#!/usr/bin/env python3
"""Smoke-test an extracted plugin package using only its verified runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CONFIGS = {
    "s2t", "t2s", "s2tw", "tw2s", "s2twp", "tw2sp", "s2hk", "hk2s",
    "s2hkp", "hk2sp", "t2tw", "tw2t", "t2hk", "hk2t", "t2jp", "jp2t",
    "s2t_jieba", "s2tw_jieba", "s2twp_jieba", "s2hk_jieba", "s2hkp_jieba",
    "tw2sp_jieba", "hk2sp_jieba",
}


def load_expectations(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            case = json.loads(line)
        except ValueError as exc:
            raise SystemExit(f"invalid package smoke JSONL at {path}:{line_number}") from exc
        if not isinstance(case, dict) or any(
            not isinstance(case.get(key), str)
            for key in ("id", "config", "source", "expected")
        ):
            raise SystemExit(f"invalid package smoke case at {path}:{line_number}")
        cases.append(case)
    configs = [case["config"] for case in cases]
    if len(configs) != len(set(configs)) or set(configs) != EXPECTED_CONFIGS:
        raise SystemExit("package smoke expectations must contain every supported config once")
    return cases


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _verify_import_origins(plugin_root: Path, payload_root: Path) -> None:
    for prefix, expected_root in (
        ("app", plugin_root),
        ("opencc_backend", plugin_root),
        ("opencc", payload_root),
    ):
        for name, module in tuple(sys.modules.items()):
            if name != prefix and not name.startswith(prefix + "."):
                continue
            module_file = getattr(module, "__file__", None)
            if module_file is None:
                continue
            origin = Path(module_file).resolve()
            if not _is_within(origin, expected_root):
                raise SystemExit(f"{name} imported outside extracted package roots: {origin}")


def run_smoke(
    plugin_root: Path,
    *,
    expected_runtime: str,
    expectations: Path,
) -> Mapping[str, object]:
    plugin_root = plugin_root.resolve()
    manifest_path = plugin_root / "vendor" / "opencc" / "manifest.json"
    if not manifest_path.is_file() or not (plugin_root / "opencc_backend").is_dir():
        raise SystemExit(f"not an extracted OpenCCForSigil plugin root: {plugin_root}")

    # The smoke checks import code from the supplied extraction only and must
    # leave every payload byte-for-byte free of interpreter caches.
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    plugin_root_text = str(plugin_root)
    sys.path[:] = [plugin_root_text, *[item for item in sys.path if item != plugin_root_text]]

    from opencc_backend.backend import OpenCCBackend
    from opencc_backend.runtime_selector import RuntimeSelector

    selector = RuntimeSelector(manifest_path=manifest_path)
    backend = OpenCCBackend("s2t", selector=selector)
    try:
        runtime, payload, payload_root = selector.select()
        selected_runtime = Path(payload.payload_path).name
        if selected_runtime != expected_runtime:
            raise SystemExit(
                f"package selected {selected_runtime!r}; expected {expected_runtime!r} "
                f"for {runtime.os}/{runtime.architecture}"
            )

        import opencc

        opencc_origin = Path(opencc.__file__).resolve()
        if not _is_within(opencc_origin, payload_root):
            raise SystemExit(f"OpenCC Binding imported outside selected payload: {opencc_origin}")
        _verify_import_origins(plugin_root, payload_root)

        self_test = backend.self_test(include_optional=True)
        if not self_test.passed:
            raise SystemExit(
                "package self-test failed: "
                + json.dumps(self_test.checks, ensure_ascii=False, sort_keys=True)
                + (f" ({self_test.error})" if self_test.error else "")
            )

        cases = load_expectations(expectations)
        for case in cases:
            actual = backend.convert_for_config(case["config"], case["source"])
            if actual != case["expected"]:
                raise SystemExit(
                    f"package smoke mismatch for {case['id']} ({case['config']}): "
                    f"expected {case['expected']!r}, got {actual!r}"
                )

        cache_dirs = [path for path in plugin_root.rglob("__pycache__") if path.is_dir()]
        bytecode_files = list(plugin_root.rglob("*.pyc"))
        if cache_dirs or bytecode_files:
            raise SystemExit(
                "package smoke wrote Python bytecode: "
                + ", ".join(str(path) for path in (cache_dirs + bytecode_files)[:10])
            )
        return {
            "runtime": selected_runtime,
            "self_test": self_test.checks,
            "conversion_cases": len(cases),
        }
    finally:
        backend.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--expected-runtime", required=True)
    parser.add_argument(
        "--expectations",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "package_smoke.jsonl",
    )
    args = parser.parse_args()
    result = run_smoke(
        args.plugin_root,
        expected_runtime=args.expected_runtime,
        expectations=args.expectations,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

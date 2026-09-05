#!/usr/bin/env python3
"""Build and vendor the official OpenCC native Jieba plugin.

This is a Build/Release-only command. It builds the pinned upstream
``plugins/jieba`` sources against the selected official Python wheel payload's
same-release OpenCC static library. Runtime never runs CMake, downloads source,
or compiles a plugin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping
import uuid


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugin" / "OpenCCForSigil"
VENDOR_ROOT = PLUGIN_ROOT / "vendor" / "opencc"
MANIFEST_PATH = VENDOR_ROOT / "manifest.json"
JIEBA_PLUGIN_NAME = "opencc-jieba"
JIEBA_CONFIGS = (
    "s2t_jieba",
    "s2tw_jieba",
    "s2twp_jieba",
    "s2hk_jieba",
    "s2hkp_jieba",
    "tw2sp_jieba",
    "hk2sp_jieba",
)


def _files(root: Path) -> Iterable[Path]:
    return (path for path in root.rglob("*") if path.is_file())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(_files(root), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_hash(values: Mapping[str, str]) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _data_manifest(payload_root: Path) -> dict[str, str]:
    share_root = payload_root / "opencc" / "clib" / "share" / "opencc"
    return {
        path.relative_to(payload_root).as_posix(): _sha256_file(path)
        for path in sorted(_files(share_root), key=lambda item: item.relative_to(payload_root).as_posix())
    }


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _source_commit(source_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(f"OpenCC source is not a git checkout: {source_root}")
    return result.stdout.strip()


def _payload_for_current_runtime():
    sys.path.insert(0, str(PLUGIN_ROOT))
    from opencc_backend.runtime_selector import RuntimeSelector

    return RuntimeSelector().select()


def _safe_payload_path(payload_root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SystemExit(f"payload path escapes selected payload: {relative}")
    resolved = (payload_root / candidate).resolve()
    if payload_root.resolve() not in resolved.parents:
        raise SystemExit(f"payload path escapes selected payload: {relative}")
    return resolved


def _platform_paths(payload_root: Path, runtime_os: str) -> tuple[Path, Path]:
    if runtime_os == "windows":
        plugin_dir = payload_root / "opencc" / "clib" / "bin" / "plugins"
    elif (payload_root / "opencc" / "clib" / "lib64").is_dir():
        plugin_dir = payload_root / "opencc" / "clib" / "lib64" / "opencc" / "plugins"
    else:
        plugin_dir = payload_root / "opencc" / "clib" / "lib" / "opencc" / "plugins"
    share_dir = payload_root / "opencc" / "clib" / "share" / "opencc"
    return plugin_dir, share_dir


def _opencc_cmake_dir(clib_root: Path) -> Path:
    candidates = (
        clib_root / "lib" / "cmake" / "opencc",
        clib_root / "lib64" / "cmake" / "opencc",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise SystemExit(
        "wheel does not contain the official OpenCC CMake package: "
        + ", ".join(str(candidate) for candidate in candidates)
    )


def _find_plugin(install_root: Path) -> Path:
    candidates = sorted(
        path
        for path in install_root.rglob("*")
        if path.is_file()
        and "opencc-jieba" in path.name.lower()
        and path.suffix.lower() in {".dll", ".dylib", ".so"}
    )
    if len(candidates) != 1:
        raise SystemExit(
            "expected exactly one installed official opencc-jieba shared plugin; "
            f"found: {', '.join(str(path) for path in candidates)}"
        )
    return candidates[0]


def _cmake_rpath(runtime_os: str) -> str | None:
    if runtime_os == "macos":
        return "@loader_path"
    if runtime_os == "linux":
        return "$ORIGIN"
    return None


def _strip_plugin(plugin_library: Path, runtime_os: str) -> None:
    """Remove build-time symbols and paths before hashing the release payload."""

    if runtime_os == "macos":
        _run(["strip", "-S", "-x", str(plugin_library)])
    elif runtime_os == "linux" and shutil.which("strip"):
        _run(["strip", "--strip-unneeded", str(plugin_library)])
    # The Windows CMake toolchain normally emits a release DLL without a PDB
    # embedded in the payload.  Do not require a Unix strip utility there.


def _build_plugin(
    source_root: Path, payload_root: Path, runtime_os: str, build_root: Path
) -> tuple[Path, Path]:
    plugin_source = source_root / "plugins" / "jieba"
    if not (plugin_source / "CMakeLists.txt").is_file():
        raise SystemExit(f"official OpenCC Jieba plugin source is missing: {plugin_source}")
    clib_root = payload_root / "opencc" / "clib"
    opencc_dir = _opencc_cmake_dir(clib_root)

    install_root = build_root / "install"
    configure = [
        "cmake",
        "-S",
        str(plugin_source),
        "-B",
        str(build_root / "cmake"),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={install_root}",
        f"-DOpenCC_DIR={opencc_dir}",
        f"-DCMAKE_PREFIX_PATH={clib_root}",
        "-DOPENCC_ENABLE_INSTALL=ON",
        "-DBUILD_SHARED_LIBS=OFF",
    ]
    if runtime_os != "windows":
        configure.append(f"-DCMAKE_CXX_FLAGS_RELEASE=-ffile-prefix-map={source_root}=.")
    rpath = _cmake_rpath(runtime_os)
    if rpath is not None:
        configure.extend(
            [
                f"-DCMAKE_INSTALL_RPATH={rpath}",
                "-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON",
            ]
        )
    build_environment = os.environ.copy()
    if runtime_os == "windows":
        # Official Windows wheels keep the repaired MSVC runtime in
        # ``opencc.libs``.  CMake must find and execute the wheel's
        # ``opencc_dict.exe`` while generating the merged Jieba dictionary.
        runtime_dirs = (
            payload_root / "opencc.libs",
            clib_root / "bin",
        )
        build_environment["PATH"] = os.pathsep.join(
            [str(path) for path in runtime_dirs if path.is_dir()]
            + [build_environment.get("PATH", "")]
        )
    _run(configure, env=build_environment)
    _run(
        [
            "cmake",
            "--build",
            str(build_root / "cmake"),
            "--config",
            "Release",
            "--parallel",
        ],
        env=build_environment,
    )
    _run(
        ["cmake", "--install", str(build_root / "cmake"), "--config", "Release"],
        env=build_environment,
    )
    plugin_library = _find_plugin(install_root)
    _strip_plugin(plugin_library, runtime_os)
    return plugin_library, install_root


def _copy_plugin_payload(
    *,
    payload_root: Path,
    runtime_os: str,
    plugin_library: Path,
    install_root: Path,
) -> dict[str, Any]:
    plugin_dir, share_dir = _platform_paths(payload_root, runtime_os)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    share_dir.mkdir(parents=True, exist_ok=True)

    for existing in plugin_dir.iterdir():
        if "opencc-jieba" in existing.name.lower() and existing.is_file():
            existing.unlink()
    target_library = plugin_dir / plugin_library.name
    shutil.copy2(plugin_library, target_library)

    installed_share = install_root / "share" / "opencc"
    for config in JIEBA_CONFIGS:
        source = installed_share / f"{config}.json"
        if not source.is_file():
            raise SystemExit(f"official Jieba config was not installed: {source}")
        shutil.copy2(source, share_dir / source.name)
    installed_dict = installed_share / "jieba_dict"
    if not installed_dict.is_dir():
        raise SystemExit(f"official Jieba dictionary was not installed: {installed_dict}")
    destination_dict = share_dir / "jieba_dict"
    destination_dict.mkdir(parents=True, exist_ok=True)
    for source in _files(installed_dict):
        shutil.copy2(source, destination_dict / source.name)

    resource_paths = [share_dir / f"{config}.json" for config in JIEBA_CONFIGS]
    resource_paths.extend(sorted(_files(destination_dict)))
    resource_hashes = {
        path.relative_to(payload_root).as_posix(): _sha256_file(path)
        for path in sorted(resource_paths, key=lambda item: item.relative_to(payload_root).as_posix())
    }
    library_path = target_library.relative_to(payload_root).as_posix()
    plugin_dir_path = plugin_dir.relative_to(payload_root).as_posix()
    return {
        "name": JIEBA_PLUGIN_NAME,
        "kind": "segmentation",
        "upstream_version": "",
        "upstream_tag": "",
        "upstream_commit": "",
        "plugin_dir": plugin_dir_path,
        "library_path": library_path,
        "library_sha256": _sha256_file(target_library),
        "config_names": list(JIEBA_CONFIGS),
        "resource_hashes": resource_hashes,
        "resource_manifest_sha256": _canonical_hash(resource_hashes),
        "build_profile": "official OpenCC plugins/jieba against same-release vendored static core",
    }


def build(source_root: Path, payload_root: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_commit = str(manifest.get("opencc_upstream_commit", ""))
    actual_commit = _source_commit(source_root)
    if actual_commit != expected_commit:
        raise SystemExit(
            f"OpenCC source commit mismatch: manifest={expected_commit}, source={actual_commit}"
        )

    payload_root = payload_root.resolve()
    payload_records = manifest.get("payloads", [])
    matching = [
        record
        for record in payload_records
        if VENDOR_ROOT.joinpath(str(record.get("payload_path", ""))).resolve() == payload_root
    ]
    if len(matching) != 1:
        raise SystemExit(f"manifest does not identify exactly one payload: {payload_root}")
    record = matching[0]
    runtime_os = str(record["os"])
    with tempfile.TemporaryDirectory(prefix="opencc-jieba-", dir=ROOT / "native_build" / "work") as temp:
        plugin_library, install_root = _build_plugin(
            source_root,
            payload_root,
            runtime_os,
            Path(temp),
        )
        plugin_record = _copy_plugin_payload(
            payload_root=payload_root,
            runtime_os=runtime_os,
            plugin_library=plugin_library,
            install_root=install_root,
        )

    plugin_record["upstream_version"] = str(manifest["opencc_version"])
    plugin_record["upstream_tag"] = str(manifest["opencc_upstream_tag"])
    plugin_record["upstream_commit"] = expected_commit
    record["native_plugins"] = {JIEBA_PLUGIN_NAME: plugin_record}
    record["config_hashes"] = {
        **dict(record.get("config_hashes", {})),
        **{
            config: _sha256_file(payload_root / "opencc" / "clib" / "share" / "opencc" / f"{config}.json")
            for config in JIEBA_CONFIGS
        },
    }
    data_files = _data_manifest(payload_root)
    record["config_data"] = {
        "source": (
            f"official OpenCC {manifest['opencc_version']} wheel payload plus official "
            "opencc-jieba plugin resources"
        ),
        "manifest_sha256": _canonical_hash(data_files),
        "files": data_files,
    }
    manifest["config_data"] = {
        "source": "per-payload official OpenCC wheel/config/data provenance",
        "payloads": {
            str(item["payload_path"]): item["config_data"]
            for item in manifest.get("payloads", [])
            if isinstance(item, dict) and isinstance(item.get("config_data"), dict)
        },
    }
    record["payload_sha256"] = _sha256_tree(payload_root)
    temporary = MANIFEST_PATH.with_name(f".{MANIFEST_PATH.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST_PATH)
    print(f"vendored official {JIEBA_PLUGIN_NAME} for {record['payload_path']}")
    print(f"plugin sha256: {plugin_record['library_sha256']}")
    print(f"payload sha256: {record['payload_sha256']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="pinned BYVoid/OpenCC source checkout")
    parser.add_argument(
        "--payload-root",
        type=Path,
        help="selected extracted wheel payload; defaults to the current runtime payload",
    )
    args = parser.parse_args()
    if not (ROOT / "native_build" / "work").is_dir():
        (ROOT / "native_build" / "work").mkdir(parents=True, exist_ok=True)
    if args.payload_root is None:
        _, _, payload_root = _payload_for_current_runtime()
    else:
        payload_root = args.payload_root.resolve()
    build(args.source.resolve(), payload_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

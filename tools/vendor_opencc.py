#!/usr/bin/env python3
"""Fetch, verify, extract, and register an official OpenCC Python wheel.

This is a Build/Release-only tool.  It never runs from the installed plugin,
never invokes pip, and never resolves a dependency from the host environment.
The selected wheel is identified by its exact PyPI filename and SHA-256 digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from time import sleep
from typing import Any, Iterable, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen
import uuid
import zipfile

from fetch_opencc_wheels import fetch_metadata


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "opencc"
MANIFEST_PATH = VENDOR_ROOT / "manifest.json"
WHEEL_CACHE = ROOT / "native_build" / "work" / "wheels"
USER_AGENT = "OpenCCForSigil-build/0.1 (+official-wheel-vendor)"
V1_CONFIGS = (
    "s2t",
    "t2s",
    "s2tw",
    "tw2s",
    "s2twp",
    "tw2sp",
    "s2hk",
    "hk2s",
    "s2hkp",
    "hk2sp",
    "t2tw",
    "t2hk",
    "tw2t",
    "hk2t",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    return (path for path in root.rglob("*") if path.is_file())


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(_iter_files(root), key=lambda path: path.relative_to(root).as_posix())
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _download_verified(url: str, destination: Path, expected_sha256: str, expected_size: int | None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if (
        destination.is_file()
        and (expected_size is None or destination.stat().st_size == expected_size)
        and _sha256_file(destination) == expected_sha256
    ):
        print(f"reusing verified wheel {destination}")
        return destination

    last_error: Exception | None = None
    for attempt in range(4):
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    handle.write(chunk)
            actual_size = temporary.stat().st_size
            actual = _sha256_file(temporary)
            if expected_size is not None and actual_size != expected_size:
                raise RuntimeError(
                    f"wheel size mismatch: expected {expected_size}, got {actual_size}"
                )
            if actual != expected_sha256:
                raise RuntimeError(
                    f"wheel SHA-256 mismatch: expected {expected_sha256}, got {actual}"
                )
            temporary.replace(destination)
            print(f"downloaded and verified {destination.name}")
            return destination
        except (OSError, URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt == 3:
                raise RuntimeError(f"could not download and verify official wheel {url}") from exc
            sleep(1 << attempt)
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError("unreachable wheel download state") from last_error


def _safe_extract(wheel: Path, destination: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe path in wheel: {member.filename!r}")
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            mode = (member.external_attr >> 16) & 0o777
            if stat.S_ISLNK((member.external_attr >> 16) & 0xFFFF):
                raise RuntimeError(f"symlink entries are not accepted in wheel payloads: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if mode:
                target.chmod(mode)


def _runtime_from_wheel(filename: str) -> tuple[str, int, int, str, str, str]:
    if not filename.endswith(".whl"):
        raise RuntimeError(f"not a wheel filename: {filename}")
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        raise RuntimeError(f"cannot parse wheel filename: {filename}")
    python_tag, abi_tag, platform_tag = parts[-3:]
    if python_tag != abi_tag or not python_tag.startswith("cp") or not python_tag[2:].isdigit():
        raise RuntimeError(f"wheel is not a CPython ABI-specific wheel: {filename}")
    digits = python_tag[2:]
    if len(digits) != 3:
        raise RuntimeError(f"unexpected CPython wheel tag: {python_tag}")
    major, minor = int(digits[0]), int(digits[1:])
    if (major, minor, python_tag) != (3, 14, "cp314"):
        raise RuntimeError(f"wheel is outside the V1 CPython 3.14/cp314 policy: {filename}")

    if platform_tag.startswith("macosx_"):
        os_name = "macos"
        architecture = platform_tag.rsplit("_", 1)[-1]
    elif platform_tag.startswith("win_"):
        os_name = "windows"
        architecture = "x86_64" if platform_tag == "win_amd64" else platform_tag.rsplit("_", 1)[-1]
    elif platform_tag.startswith("manylinux"):
        os_name = "linux"
        if "aarch64" in platform_tag:
            architecture = "aarch64"
        elif "x86_64" in platform_tag:
            architecture = "x86_64"
        else:
            raise RuntimeError(f"unsupported Linux wheel architecture: {filename}")
    else:
        raise RuntimeError(f"unsupported wheel platform tag: {filename}")
    if architecture not in {"arm64", "aarch64", "x86_64"}:
        raise RuntimeError(f"unsupported wheel architecture: {filename}")
    return "CPython", major, minor, python_tag, os_name, architecture


def _host_platform() -> tuple[str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin":
        os_name = "macos"
        architecture = "arm64" if machine == "arm64" else "x86_64" if machine in {"x86_64", "amd64"} else machine
    elif system == "Windows":
        os_name = "windows"
        architecture = "x86_64" if machine in {"amd64", "x86_64"} else machine
    elif system == "Linux":
        os_name = "linux"
        architecture = "aarch64" if machine in {"aarch64", "arm64"} else "x86_64" if machine in {"x86_64", "amd64"} else machine
    else:
        raise RuntimeError(f"unsupported build host platform: {system}/{machine}")
    return os_name, architecture


def _select_wheel(wheels: list[Mapping[str, Any]], wheel_name: str | None) -> Mapping[str, Any]:
    if wheel_name:
        matches = [item for item in wheels if item.get("filename") == wheel_name]
    else:
        host_os, host_architecture = _host_platform()
        matches = []
        for item in wheels:
            name = str(item.get("filename", ""))
            try:
                _, major, minor, abi, os_name, architecture = _runtime_from_wheel(name)
            except RuntimeError:
                continue
            if (major, minor, abi, os_name, architecture) == (3, 14, "cp314", host_os, host_architecture):
                matches.append(item)
    if len(matches) != 1:
        available = ", ".join(str(item.get("filename")) for item in wheels if item.get("filename"))
        requested = wheel_name or "the current build host"
        raise RuntimeError(f"expected exactly one official wheel for {requested}; available: {available}")
    selected = matches[0]
    for key in ("filename", "url", "sha256"):
        if not selected.get(key):
            raise RuntimeError(f"PyPI wheel metadata is missing {key}")
    return selected


def _verify_wheel_metadata(wheel_root: Path, version: str) -> None:
    metadata_files = sorted(wheel_root.glob("*.dist-info/METADATA"))
    if len(metadata_files) != 1:
        raise RuntimeError("official wheel must contain exactly one dist-info METADATA file")
    fields: dict[str, str] = {}
    for line in metadata_files[0].read_text(encoding="utf-8").splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            fields.setdefault(key.lower(), value.strip())
    if fields.get("name", "").lower() != "opencc" or fields.get("version") != version:
        raise RuntimeError(
            f"wheel metadata mismatch: name={fields.get('name')!r}, version={fields.get('version')!r}"
        )
    if not (wheel_root / "opencc" / "__init__.py").is_file():
        raise RuntimeError("official wheel does not contain the opencc Python package")
    if not list((wheel_root / "opencc" / "clib" / "share" / "opencc").glob("*.json")):
        raise RuntimeError("official wheel does not contain OpenCC config data")


def _run_import_self_test(payload_root: Path, version: str) -> None:
    script = r'''
import importlib
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
expected_version = sys.argv[2]
sys.path.insert(0, str(root))
module = importlib.import_module("opencc")
origin = Path(module.__file__).resolve()
if root not in origin.parents:
    raise SystemExit(f"opencc imported outside payload: {origin}")
if str(getattr(module, "__version__", "")) != expected_version:
    raise SystemExit(f"unexpected OpenCC version: {getattr(module, '__version__', None)!r}")
required = {"s2t", "t2s", "s2tw", "tw2s", "s2twp", "tw2sp", "s2hk", "hk2s", "s2hkp", "hk2sp", "t2tw", "t2hk", "tw2t", "hk2t"}
available = {str(item).removesuffix(".json") for item in module.CONFIGS}
if not required <= available:
    raise SystemExit(f"missing V1 configs: {sorted(required - available)}")
if module.OpenCC("s2t").convert("汉字") != "漢字":
    raise SystemExit("s2t smoke failed")
if module.OpenCC("t2s").convert("漢字") != "汉字":
    raise SystemExit("t2s smoke failed")
for config in sorted(required):
    module.OpenCC(config)
print("official OpenCC Python Binding import/config/smoke self-test passed")
'''
    environment = os.environ.copy()
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-B", "-I", "-c", script, str(payload_root), version],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"official OpenCC payload self-test failed: {detail}")
    print(result.stdout.strip())


def _data_manifest(payload_root: Path) -> tuple[dict[str, str], dict[str, str], str]:
    share_root = payload_root / "opencc" / "clib" / "share" / "opencc"
    files: dict[str, str] = {}
    config_hashes: dict[str, str] = {}
    for path in sorted(_iter_files(share_root), key=lambda item: item.relative_to(payload_root).as_posix()):
        relative = path.relative_to(payload_root).as_posix()
        digest = _sha256_file(path)
        files[relative] = digest
        if path.suffix == ".json":
            config_hashes[path.stem] = digest
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return files, config_hashes, hashlib.sha256(canonical).hexdigest()


def _replace_payload(staging: Path, target: Path) -> None:
    backup: Path | None = None
    if target.exists():
        backup = target.with_name(f".{target.name}.previous-{uuid.uuid4().hex}")
        target.rename(backup)
    try:
        staging.rename(target)
    except Exception:
        if backup is not None and not target.exists():
            backup.rename(target)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def _write_manifest(manifest: dict[str, Any]) -> None:
    temporary = MANIFEST_PATH.with_name(f".{MANIFEST_PATH.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST_PATH)


def vendor(version: str, wheel_name: str | None, skip_import_test: bool) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("opencc_version") != version:
        raise RuntimeError(
            f"manifest pins OpenCC {manifest.get('opencc_version')!r}; requested {version!r}"
        )
    metadata = fetch_metadata(version)
    wheels = [
        {
            "filename": item.get("filename"),
            "sha256": item.get("digests", {}).get("sha256"),
            "size": item.get("size"),
            "url": item.get("url"),
        }
        for item in metadata.get("urls", [])
        if str(item.get("filename", "")).endswith(".whl")
    ]
    selected = _select_wheel(wheels, wheel_name)
    filename = str(selected["filename"])
    _, major, minor, abi, os_name, architecture = _runtime_from_wheel(filename)
    payload_id = f"{os_name}-{architecture}-{abi}"
    payloads_root = VENDOR_ROOT / "payloads"
    payloads_root.mkdir(parents=True, exist_ok=True)
    cache_path = WHEEL_CACHE / filename
    wheel = _download_verified(
        str(selected["url"]),
        cache_path,
        str(selected["sha256"]),
        int(selected["size"]) if selected.get("size") is not None else None,
    )

    temporary_root = Path(tempfile.mkdtemp(prefix=".staging-", dir=payloads_root))
    target = payloads_root / payload_id
    try:
        _safe_extract(wheel, temporary_root)
        _verify_wheel_metadata(temporary_root, version)
        if not skip_import_test:
            _run_import_self_test(temporary_root, version)
        files, config_hashes, data_manifest_sha256 = _data_manifest(temporary_root)
        payload_sha256 = _sha256_tree(temporary_root)
        _replace_payload(temporary_root, target)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise

    record = {
        "python_implementation": "CPython",
        "python_version": f"{major}.{minor}",
        "python_abi": abi,
        "python_build_version": platform.python_version(),
        "os": os_name,
        "architecture": architecture,
        "wheel_name": filename,
        "wheel_sha256": str(selected["sha256"]),
        "wheel_url": str(selected["url"]),
        "payload_path": f"payloads/{payload_id}",
        "payload_sha256": payload_sha256,
        "payload_runtime_test": "skipped-cross-platform" if skip_import_test else "passed",
        "config_hashes": config_hashes,
    }
    payloads = [
        item for item in manifest.get("payloads", [])
        if not (
            item.get("python_implementation") == record["python_implementation"]
            and item.get("python_version") == record["python_version"]
            and item.get("python_abi") == record["python_abi"]
            and item.get("os") == record["os"]
            and item.get("architecture") == record["architecture"]
        )
    ]
    payloads.append(record)
    payloads.sort(key=lambda item: (item["os"], item["architecture"], item["python_abi"]))
    manifest["status"] = "phase1-payload-verified"
    manifest["payloads"] = payloads
    manifest["config_data"] = {
        "source": f"official OpenCC {version} wheel payload: opencc/clib/share/opencc",
        "manifest_sha256": data_manifest_sha256,
        "files": files,
    }
    _write_manifest(manifest)
    print(f"registered official OpenCC payload {payload_id}")
    print(f"payload sha256: {payload_sha256}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="1.4.2")
    parser.add_argument("--wheel-name", help="exact official PyPI wheel filename for cross-platform builds")
    parser.add_argument(
        "--skip-import-test",
        action="store_true",
        help="allow cross-platform packaging when the native payload cannot run on this build host",
    )
    args = parser.parse_args()
    vendor(args.version, args.wheel_name, args.skip_import_test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

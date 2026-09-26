#!/usr/bin/env python3
"""Fetch, extract, and verify one locked Python regex runtime wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

try:
    from runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES, format_runtime_identity
    from native_compatibility import NativeCompatibilityError, validate_binary_path
except ModuleNotFoundError:  # Imported as tools.regex_payload by tests.
    from tools.runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES, format_runtime_identity
    from tools.native_compatibility import NativeCompatibilityError, validate_binary_path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "native_build" / "regex-wheel-lock.json"
LICENSE_PATH = ROOT / "plugin" / "OpenCCForSigil" / "resources" / "third_party" / "REGEX_LICENSE.txt"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_FILES = {"regex/__init__.py", "regex/_main.py", "regex/_regex_core.py"}
DIST_INFO_PREFIX = "regex-2026.9.10.dist-info/"
KNOWN_WHEEL_METADATA = {
    DIST_INFO_PREFIX + "METADATA",
    DIST_INFO_PREFIX + "RECORD",
    DIST_INFO_PREFIX + "WHEEL",
    DIST_INFO_PREFIX + "top_level.txt",
    DIST_INFO_PREFIX + "licenses/LICENSE.txt",
    "regex/tests/test_regex.py",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in regex payloads: {path}")
        if not path.is_file() or path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def runtime_identity() -> tuple[str, str, str, str, str]:
    implementation = "CPython" if sys.implementation.name == "cpython" else sys.implementation.name
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    abi = str(getattr(sys.implementation, "cache_tag", "")).removeprefix("cpython-")
    abi = "cp" + abi if abi else f"cp{sys.version_info.major}{sys.version_info.minor}"
    os_name = "macos" if sys.platform == "darwin" else (
        "windows" if sys.platform.startswith("win") else
        "linux" if sys.platform.startswith("linux") else sys.platform
    )
    architecture = platform.machine().lower()
    architecture = {
        "amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64",
        "aarch64": "aarch64",
    }.get(architecture, architecture)
    return implementation, version, abi, os_name, architecture


def payload_id(identity: tuple[str, str, str, str, str]) -> str:
    _implementation, _version, abi, os_name, architecture = identity
    return f"{os_name}-{architecture}-{abi}"


def load_lock(path: Path = LOCK_PATH) -> dict:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read regex wheel lock: {exc}") from exc
    if lock.get("package") != "regex" or lock.get("version") != "2026.9.10":
        raise ValueError("regex wheel lock has an unsupported package or version")
    wheels = lock.get("wheels")
    if not isinstance(wheels, list):
        raise ValueError("regex wheel lock wheels must be a list")
    identities = [tuple(item.get(key) for key in (
        "python_implementation", "python_version", "python_abi", "os", "architecture"
    )) for item in wheels if isinstance(item, dict)]
    if len(identities) != len(wheels) or len(set(identities)) != len(identities):
        raise ValueError("regex wheel lock identities must be unique records")
    if set(identities) != set(SUPPORTED_RUNTIME_IDENTITIES):
        raise ValueError("regex wheel lock does not match the supported runtime matrix")
    for record, identity in zip(wheels, identities):
        filename, url, digest = record.get("filename"), record.get("url"), record.get("sha256")
        if not isinstance(filename, str) or not filename.startswith("regex-2026.9.10-") \
                or not filename.endswith(".whl"):
            raise ValueError("regex wheel lock contains an invalid wheel filename")
        if not isinstance(url, str) or not url.startswith("https://files.pythonhosted.org/") \
                or not url.endswith("/" + filename):
            raise ValueError("regex wheel URL must be the official PyPI file URL")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ValueError("regex wheel SHA-256 is malformed")
        expected_tag = f"-{identity[2]}-{identity[2]}-"
        if expected_tag not in filename:
            raise ValueError(f"regex wheel ABI does not match {format_runtime_identity(identity)}")
    return lock


def _wheel_record(lock: dict, identity: tuple[str, ...]) -> dict:
    for record in lock["wheels"]:
        candidate = tuple(record[key] for key in (
            "python_implementation", "python_version", "python_abi", "os", "architecture"
        ))
        if candidate == identity:
            return record
    raise ValueError("regex wheel lock has no wheel for " + format_runtime_identity(identity))


def _assert_safe_output(output: Path) -> Path:
    plugin_root = (ROOT / "plugin" / "OpenCCForSigil").resolve()
    resolved = output.resolve()
    if resolved == plugin_root or plugin_root in resolved.parents or resolved in plugin_root.parents:
        raise ValueError("regex payload output must not overlap the plugin source tree")
    return resolved


def _download_wheel(record: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = "curl.exe" if os.name == "nt" else "curl"
    subprocess.run(
        [command, "--fail", "--location", "--retry", "3", "--silent", "--show-error",
         "--output", str(destination), record["url"]],
        check=True,
    )
    actual = sha256_file(destination)
    if actual != record["sha256"]:
        raise ValueError(
            f"regex wheel SHA-256 mismatch for {record['filename']}: {actual}"
        )


def _extract_wheel(wheel: Path, destination: Path, *, runtime_os: str, architecture: str) -> dict[str, str]:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            if len(names) != len(set(names)):
                raise ValueError("regex wheel contains duplicate member paths")
            extensions = [name for name in names
                          if name.startswith("regex/_regex.") and name.rsplit(".", 1)[-1] in {"so", "pyd"}]
            if len(extensions) != 1:
                raise ValueError("regex wheel must contain exactly one native regex extension")
            required = PACKAGE_FILES | set(extensions) | KNOWN_WHEEL_METADATA
            unknown = sorted(set(names) - required)
            missing = sorted((PACKAGE_FILES | set(extensions) | {
                DIST_INFO_PREFIX + "licenses/LICENSE.txt"
            }) - set(names))
            if unknown or missing:
                details = []
                if unknown:
                    details.append("unreviewed=" + ", ".join(unknown))
                if missing:
                    details.append("missing=" + ", ".join(missing))
                raise ValueError("regex wheel member list changed: " + "; ".join(details))
            license_bytes = archive.read(DIST_INFO_PREFIX + "licenses/LICENSE.txt")
            if not LICENSE_PATH.is_file() or LICENSE_PATH.read_bytes() != license_bytes:
                raise ValueError("bundled regex license does not match the locked upstream wheel")
            extension = destination / extensions[0]
            extension.parent.mkdir(parents=True, exist_ok=True)
            for relative in PACKAGE_FILES | set(extensions):
                target = destination / PurePosixPath(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(relative))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"regex wheel is not a valid ZIP archive: {wheel}") from exc
    try:
        validate_binary_path(extension, runtime_os=runtime_os, architecture=architecture)
    except NativeCompatibilityError as exc:
        raise ValueError(f"regex extension compatibility check failed: {exc}") from exc
    return {
        path.relative_to(destination).as_posix(): sha256_file(path)
        for path in sorted(destination.rglob("*")) if path.is_file()
    }


def _verify_import(package_parent: Path, version: str) -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import regex; "
        "assert regex.__version__ == sys.argv[2], regex.__version__; "
        "assert regex.search(r'(?V1)(?P<han>[漢字]+)', '前漢字后').group('han') == '漢字'; "
        "assert regex.search(r'(?V1)(?P<n>\\d+)', 'x12').group('n') == '12'; "
        "assert regex.compile(r'(?V1)(a+)+$').search('aaaa!', timeout=1.0) is None"
    )
    subprocess.run(
        [sys.executable, "-B", "-I", "-c", code, str(package_parent), version],
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def export(output: Path, *, wheel_path: Path | None = None) -> Path:
    lock = load_lock()
    identity = runtime_identity()
    record = _wheel_record(lock, identity)
    output = _assert_safe_output(output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="regex-wheel-", dir=output.parent) as temp:
        wheel = wheel_path or Path(temp) / record["filename"]
        if wheel_path is None:
            _download_wheel(record, wheel)
        if not wheel.is_file() or wheel.name != record["filename"]:
            raise ValueError(f"unexpected regex wheel path: {wheel}")
        if sha256_file(wheel) != record["sha256"]:
            raise ValueError(f"regex wheel SHA-256 mismatch: {wheel}")
        package_root = output / "payload"
        files = _extract_wheel(
            wheel, package_root, runtime_os=identity[3], architecture=identity[4])
        payload_hash = sha256_tree(package_root)
        _verify_import(package_root, lock["version"])
    export_record = {
        "schema_version": 1,
        "package": "regex",
        "version": lock["version"],
        "python_implementation": identity[0],
        "python_version": identity[1],
        "python_abi": identity[2],
        "os": identity[3],
        "architecture": identity[4],
        "payload_path": "payloads/" + payload_id(identity),
        "wheel_filename": record["filename"],
        "wheel_url": record["url"],
        "wheel_sha256": record["sha256"],
        "payload_sha256": payload_hash,
        "files": files,
    }
    (output / "record.json").write_text(
        json.dumps(export_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"exported verified regex {payload_id(identity)} payload to {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

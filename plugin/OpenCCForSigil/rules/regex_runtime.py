"""Load the pinned regex runtime bundled with the plugin on demand."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import threading
from types import ModuleType


REGEX_VERSION = "2026.9.10"
IDENTITY_KEYS = (
    "python_implementation", "python_version", "python_abi", "os", "architecture"
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "regex"
_LOADED_MODULE: ModuleType | None = None
_LOADED_ROOT: Path | None = None
_LOAD_LOCK = threading.RLock()


class RegexRuntimeError(RuntimeError):
    """The pinned regular-expression runtime is unavailable or unverifiable."""


def _runtime_identity() -> tuple[str, str, str, str, str]:
    implementation = "CPython" if sys.implementation.name == "cpython" else sys.implementation.name
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    cache_tag = str(getattr(sys.implementation, "cache_tag", ""))
    abi = "cp" + cache_tag.removeprefix("cpython-") if cache_tag else (
        f"cp{sys.version_info.major}{sys.version_info.minor}")
    os_name = (
        "macos" if sys.platform == "darwin" else
        "windows" if sys.platform.startswith("win") else
        "linux" if sys.platform.startswith("linux") else sys.platform
    )
    architecture = platform.machine().lower()
    architecture = {
        "amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64",
        "aarch64": "aarch64",
    }.get(architecture, architecture)
    return implementation, version, abi, os_name, architecture


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise RegexRuntimeError(f"regex payload contains a symbolic link: {path.name}")
        if not path.is_file() or path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _selected_payload() -> tuple[dict, Path]:
    manifest_path = _PACKAGE_ROOT / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegexRuntimeError(f"cannot read bundled regex manifest: {exc}") from exc
    if (manifest.get("schema_version"), manifest.get("package"), manifest.get("version")) != (
        1, "regex", REGEX_VERSION
    ):
        raise RegexRuntimeError("bundled regex manifest has an unsupported identity")
    identity = _runtime_identity()
    records = manifest.get("payloads")
    if not isinstance(records, list):
        raise RegexRuntimeError("bundled regex manifest has no payload list")
    matching = [record for record in records if isinstance(record, dict) and
                tuple(record.get(key) for key in IDENTITY_KEYS) == identity]
    if len(matching) != 1:
        raise RegexRuntimeError(
            "no single pinned regex runtime payload matches " + "/".join(identity))
    record = matching[0]
    payload_name = f"payloads/{identity[3]}-{identity[4]}-{identity[2]}"
    relative = PurePosixPath(str(record.get("payload_path", "")))
    if (relative.as_posix() != payload_name or relative.is_absolute()
            or ".." in relative.parts or "\\" in str(record.get("payload_path", ""))):
        raise RegexRuntimeError("regex payload path does not match its runtime identity")
    payload_root = (_PACKAGE_ROOT / relative).resolve()
    if _PACKAGE_ROOT.resolve() not in payload_root.parents or not payload_root.is_dir():
        raise RegexRuntimeError("regex payload path is missing or escapes the plugin tree")

    files = record.get("files")
    if not isinstance(files, dict) or not files:
        raise RegexRuntimeError("regex payload file hashes are missing")
    expected_files = {
        str(name): digest for name, digest in files.items()
        if isinstance(name, str) and isinstance(digest, str) and _HEX64.fullmatch(digest)
    }
    if expected_files != files:
        raise RegexRuntimeError("regex payload contains malformed file hash records")
    actual_files = {
        path.relative_to(payload_root).as_posix(): _sha256(path)
        for path in sorted(payload_root.rglob("*"))
        if path.is_file() and path.suffix not in {".pyc", ".pyo"}
        and "__pycache__" not in path.parts
    }
    extension_files = [name for name in actual_files
                       if name.startswith("regex/_regex.")
                       and name.rsplit(".", 1)[-1] in {"so", "pyd"}]
    known_files = {
        "regex/__init__.py", "regex/_main.py", "regex/_regex_core.py", *extension_files
    }
    if (actual_files != expected_files or set(actual_files) != known_files
            or len(extension_files) != 1):
        raise RegexRuntimeError("regex payload files differ from the verified manifest")
    payload_hash = record.get("payload_sha256")
    if not isinstance(payload_hash, str) or not _HEX64.fullmatch(payload_hash):
        raise RegexRuntimeError("regex payload tree hash is malformed")
    if _tree_sha256(payload_root) != payload_hash:
        raise RegexRuntimeError("regex payload tree hash does not match its manifest")
    if record.get("version") != REGEX_VERSION:
        raise RegexRuntimeError("regex payload version differs from the pinned version")
    wheel_digest = record.get("wheel_sha256")
    wheel_url = record.get("wheel_url")
    if (not isinstance(wheel_digest, str) or not _HEX64.fullmatch(wheel_digest)
            or not isinstance(wheel_url, str)
            or not wheel_url.startswith("https://files.pythonhosted.org/")):
        raise RegexRuntimeError("regex wheel provenance is malformed")
    return record, payload_root


def load_regex_module() -> ModuleType:
    """Return the verified bundled ``regex`` module, importing it only once."""

    with _LOAD_LOCK:
        return _load_regex_module_locked()


def _load_regex_module_locked() -> ModuleType:

    global _LOADED_MODULE, _LOADED_ROOT
    record, payload_root = _selected_payload()
    existing = sys.modules.get("regex")
    if existing is not None:
        origin = getattr(existing, "__file__", None)
        if origin is not None and Path(origin).resolve().is_relative_to(payload_root):
            if getattr(existing, "__version__", None) == REGEX_VERSION:
                for name, imported in tuple(sys.modules.items()):
                    if name != "regex" and not name.startswith("regex."):
                        continue
                    module_origin = getattr(imported, "__file__", None)
                    if (module_origin is not None
                            and not Path(module_origin).resolve().is_relative_to(payload_root)):
                        raise RegexRuntimeError(
                            f"regex submodule was loaded outside its payload: {module_origin}")
                _LOADED_MODULE, _LOADED_ROOT = existing, payload_root
                return existing
        raise RegexRuntimeError(
            "another regex package is already loaded in this Sigil process: "
            f"{getattr(existing, '__version__', 'unknown')} at {origin or 'unknown location'}")
    if _LOADED_MODULE is not None and _LOADED_ROOT == payload_root:
        sys.modules["regex"] = _LOADED_MODULE
        return _LOADED_MODULE

    package_dir = payload_root / "regex"
    init_path = package_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "regex", init_path, submodule_search_locations=[str(package_dir)])
    if spec is None or spec.loader is None:
        raise RegexRuntimeError("cannot create an import specification for bundled regex")
    module = importlib.util.module_from_spec(spec)
    sys.modules["regex"] = module
    try:
        spec.loader.exec_module(module)
        if getattr(module, "__version__", None) != REGEX_VERSION:
            raise RegexRuntimeError("bundled regex module version does not match its manifest")
        for name, imported in tuple(sys.modules.items()):
            if name != "regex" and not name.startswith("regex."):
                continue
            origin = getattr(imported, "__file__", None)
            if origin is not None and not Path(origin).resolve().is_relative_to(payload_root):
                raise RegexRuntimeError(f"regex imported a module outside its payload: {origin}")
        _LOADED_MODULE, _LOADED_ROOT = module, payload_root
        return module
    except Exception as exc:
        for name, imported in tuple(sys.modules.items()):
            if name == "regex" or name.startswith("regex."):
                origin = getattr(imported, "__file__", None)
                if origin is None or Path(origin).resolve().is_relative_to(payload_root):
                    sys.modules.pop(name, None)
        if isinstance(exc, RegexRuntimeError):
            raise
        raise RegexRuntimeError(f"cannot load bundled regex runtime: {exc}") from exc


__all__ = ["REGEX_VERSION", "RegexRuntimeError", "load_regex_module"]

"""Exact runtime detection, payload verification, and safe module import."""

from dataclasses import dataclass
import importlib
from pathlib import Path
import platform
import re
import sys
import sysconfig
from types import ModuleType
from typing import Optional, Tuple

from opencc_backend.errors import ImportOriginError, PayloadIntegrityError
from opencc_backend.integrity import verify_tree_sha256
from opencc_backend.manifest import PayloadRecord, RuntimeKey, VendorManifest


@dataclass(frozen=True)
class RuntimeInfo:
    key: RuntimeKey
    python_patch: int

    @property
    def python_implementation(self) -> str:
        return self.key.python_implementation

    @property
    def python_version(self) -> str:
        # The full version is provenance only. Payload selection uses key,
        # which intentionally contains major/minor and ABI but no patch.
        return f"{self.key.python_major}.{self.key.python_minor}.{self.python_patch}"

    @property
    def compatibility_version(self) -> str:
        return self.key.python_version

    @property
    def python_abi(self) -> str:
        return self.key.python_abi

    @property
    def os(self) -> str:
        return self.key.os

    @property
    def architecture(self) -> str:
        return self.key.architecture


def detect_runtime() -> RuntimeInfo:
    implementation = _implementation_name()
    major = sys.version_info[0]
    minor = sys.version_info[1]
    patch = sys.version_info[2]
    abi = _python_abi(major, minor)
    return RuntimeInfo(
        RuntimeKey(
            python_implementation=implementation,
            python_major=major,
            python_minor=minor,
            python_abi=abi,
            os=_normalize_os(sys.platform),
            architecture=_normalize_architecture(platform.machine()),
        ),
        python_patch=patch,
    )


class RuntimeSelector:
    """Select one exact official wheel payload and import only from it."""

    def __init__(self, manifest_path: Optional[Path] = None) -> None:
        package_root = Path(__file__).resolve().parents[1]
        self.manifest_path = manifest_path or package_root / "vendor" / "opencc" / "manifest.json"
        self._manifest: Optional[VendorManifest] = None

    @property
    def manifest(self) -> VendorManifest:
        if self._manifest is None:
            self._manifest = VendorManifest.load(self.manifest_path)
        return self._manifest

    def runtime(self) -> RuntimeInfo:
        return detect_runtime()

    def select(self) -> Tuple[RuntimeInfo, PayloadRecord, Path]:
        runtime = self.runtime()
        payload = self.manifest.select(runtime.key)
        root = self.manifest.payload_root(payload)
        if not root.is_dir():
            raise PayloadIntegrityError(f"selected OpenCC payload is missing: {root}")
        verify_tree_sha256(root, payload.payload_sha256)
        return runtime, payload, root

    def import_opencc(self) -> Tuple[ModuleType, RuntimeInfo, PayloadRecord, Path, str]:
        """Import the verified official module and return its relative origin."""

        runtime, payload, root = self.select()
        module = sys.modules.get("opencc")
        path_was_inserted = False
        if module is None:
            # The vendored payload hash covers the extracted wheel contents.
            # Runtime bytecode caches must never mutate that integrity surface.
            sys.dont_write_bytecode = True
            sys.path.insert(0, str(root))
            path_was_inserted = True
            try:
                module = importlib.import_module("opencc")
            except Exception:
                if path_was_inserted and sys.path and sys.path[0] == str(root):
                    sys.path.pop(0)
                raise
        origin = _verified_origin(module, root)
        version = str(getattr(module, "__version__", ""))
        if version != self.manifest.opencc_version:
            raise ImportOriginError(
                f"OpenCC version mismatch: manifest={self.manifest.opencc_version}, import={version}"
            )
        return module, runtime, payload, root, origin


def _implementation_name() -> str:
    name = str(getattr(sys.implementation, "name", "")).lower()
    if name == "cpython":
        return "CPython"
    return name or "unknown"


def _python_abi(major: int, minor: int) -> str:
    soabi = str(sysconfig.get_config_var("SOABI") or "")
    match = re.search(r"cpython-(\d+)(t?)(?:-|$)", soabi)
    if match:
        return f"cp{match.group(1)}{match.group(2)}"
    cache_tag = str(getattr(sys.implementation, "cache_tag", ""))
    if cache_tag.startswith("cpython-"):
        return "cp" + cache_tag.split("-", 1)[1]
    return f"cp{major}{minor}"


def _normalize_os(value: str) -> str:
    if value == "darwin":
        return "macos"
    if value.startswith("win"):
        return "windows"
    if value.startswith("linux"):
        return "linux"
    return value


def _normalize_architecture(value: str) -> str:
    normalized = value.lower()
    if normalized in {"amd64", "x86_64"}:
        return "x86_64"
    if normalized in {"arm64", "aarch64"}:
        return "arm64" if normalized == "arm64" else "aarch64"
    return normalized


def _verified_origin(module: ModuleType, payload_root: Path) -> str:
    origin_value = getattr(module, "__file__", None)
    if not origin_value:
        raise ImportOriginError("imported opencc has no __file__ origin")
    origin = Path(origin_value).resolve()
    root = payload_root.resolve()
    if root not in origin.parents:
        raise ImportOriginError(
            f"opencc imported outside selected payload: {origin} (expected under {root})"
        )
    return origin.relative_to(root).as_posix()

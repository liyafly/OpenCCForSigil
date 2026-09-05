"""Exact runtime detection, payload verification, and safe module import."""

from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import sysconfig
from types import ModuleType
from typing import Optional, Tuple

from opencc_backend.errors import ImportOriginError, PayloadIntegrityError
from opencc_backend.integrity import verify_sha256, verify_tree_sha256
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
        self._verify_native_plugins(payload, root)
        return runtime, payload, root

    def import_opencc(self) -> Tuple[ModuleType, RuntimeInfo, PayloadRecord, Path, str]:
        """Import the verified official module and return its relative origin."""

        runtime, payload, root = self.select()
        self._prepare_payload_environment(payload, root)
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

    def _verify_native_plugins(self, payload: PayloadRecord, root: Path) -> None:
        for plugin in payload.native_plugins.values():
            if plugin.upstream_version != self.manifest.opencc_version:
                raise PayloadIntegrityError(
                    f"native plugin {plugin.name} version does not match OpenCC payload"
                )
            if plugin.upstream_tag != self.manifest.upstream_tag:
                raise PayloadIntegrityError(
                    f"native plugin {plugin.name} upstream tag does not match OpenCC payload"
                )
            if plugin.upstream_commit != self.manifest.upstream_commit:
                raise PayloadIntegrityError(
                    f"native plugin {plugin.name} upstream commit does not match OpenCC payload"
                )
            plugin_dir = _payload_path(root, plugin.plugin_dir)
            if not plugin_dir.is_dir():
                raise PayloadIntegrityError(f"native plugin directory is missing: {plugin_dir}")
            library = _payload_path(root, plugin.library_path)
            if not library.is_file() or library.parent.resolve() != plugin_dir.resolve():
                raise PayloadIntegrityError(f"native plugin library is missing: {library}")
            verify_sha256(library, plugin.library_sha256)
            for relative, expected in plugin.resource_hashes.items():
                resource = _payload_path(root, relative)
                if not resource.is_file():
                    raise PayloadIntegrityError(f"native plugin resource is missing: {resource}")
                verify_sha256(resource, expected)
            manifest_hash = _canonical_hash(plugin.resource_hashes)
            if manifest_hash != plugin.resource_manifest_sha256:
                raise PayloadIntegrityError(
                    f"native plugin resource manifest hash mismatch: {plugin.name}"
                )
            for config in plugin.config_names:
                config_path = root / "opencc" / "clib" / "share" / "opencc" / f"{config}.json"
                if not config_path.is_file():
                    raise PayloadIntegrityError(f"native plugin config is missing: {config_path}")

    def _prepare_payload_environment(self, payload: PayloadRecord, root: Path) -> None:
        """Point OpenCC's optional plugin discovery only at the selected payload."""

        data_dir = root / "opencc" / "clib" / "share" / "opencc"
        if not data_dir.is_dir():
            raise PayloadIntegrityError(f"OpenCC data directory is missing: {data_dir}")
        plugin_dirs = tuple(
            str(_payload_path(root, plugin.plugin_dir))
            for plugin in payload.native_plugins.values()
        )
        os.environ["OPENCC_DATA_DIR"] = str(data_dir)
        if plugin_dirs:
            os.environ["OPENCC_SEGMENTATION_PLUGIN_PATH"] = os.pathsep.join(plugin_dirs)
        else:
            # Do not allow an inherited system/plugin-manager path to affect a
            # standard config or satisfy a plugin config accidentally.
            os.environ.pop("OPENCC_SEGMENTATION_PLUGIN_PATH", None)


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


def _payload_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PayloadIntegrityError(f"payload path escapes selected vendor payload: {relative}")
    resolved = (root / candidate).resolve()
    if root.resolve() not in resolved.parents:
        raise PayloadIntegrityError(f"payload path escapes selected vendor payload: {relative}")
    return resolved


def _canonical_hash(values: object) -> str:
    if not isinstance(values, dict):
        raise PayloadIntegrityError("native plugin resource hashes must be an object")
    canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

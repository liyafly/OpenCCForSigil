"""Exact runtime detection, payload verification, and safe module import."""

from dataclasses import dataclass
import hashlib
from importlib import abc as importlib_abc
import importlib
from importlib import machinery
from importlib.util import spec_from_file_location
import json
import os
from pathlib import Path
import platform
import re
import sys
import sysconfig
from types import ModuleType
from typing import Callable, Optional, Tuple
import weakref

from opencc_backend.errors import ImportOriginError, PayloadIntegrityError
from opencc_backend.integrity import verify_sha256, verify_tree_sha256
from opencc_backend.manifest import PayloadRecord, RuntimeKey, VendorManifest


_VERIFIED_MODULES: weakref.WeakKeyDictionary[ModuleType, Path] = weakref.WeakKeyDictionary()


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
        # The payload hash intentionally excludes interpreter caches.  Never let
        # those caches become executable input: remove preloaded OpenCC modules
        # and import source files through the strict finder below.  A verified
        # module set can be reused, but only after this selector established its
        # source/native provenance; this avoids reinitializing the native
        # extension for every backend instance.  The finder stays registered
        # while the package is cached so delayed submodule imports remain
        # source-only as well.
        if not _can_reuse_verified_modules(root):
            _purge_opencc_modules()
        else:
            # The official package's historical top-level fallback must never
            # remain available, even when the package itself is reused.
            sys.modules.pop("opencc_clib", None)
        _remove_payload_finders()
        finder = _PayloadImportFinder(root, payload.payload_sha256)
        sys.meta_path.insert(0, finder)
        try:
            module = importlib.import_module("opencc")
            origin = _verified_origin(module, root)
            _verify_imported_modules(root)
            version = str(getattr(module, "__version__", ""))
            if version != self.manifest.opencc_version:
                raise ImportOriginError(
                    f"OpenCC version mismatch: manifest={self.manifest.opencc_version}, import={version}"
                )
            _remember_verified_modules(root)
        except Exception:
            # Do not leave a partially imported package or an active finder
            # behind after a failed provenance check.
            _remove_payload_finder(finder)
            _purge_opencc_modules()
            raise
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
    return _verified_module_origin(module, payload_root)


def _verified_module_origin(module: ModuleType, payload_root: Path) -> str:
    origin_value = getattr(module, "__file__", None)
    if not origin_value:
        raise ImportOriginError("imported opencc has no __file__ origin")
    try:
        origin = Path(origin_value).resolve()
    except (OSError, TypeError, ValueError) as exc:
        raise ImportOriginError("imported OpenCC has an invalid __file__ origin") from exc
    root = payload_root.resolve()
    if root not in origin.parents:
        raise ImportOriginError(
            f"opencc imported outside selected payload: {origin} (expected under {root})"
        )
    spec = getattr(module, "__spec__", None)
    if spec is None or getattr(spec, "name", None) != getattr(module, "__name__", None):
        raise ImportOriginError("imported OpenCC module has no matching import spec")
    spec_origin = getattr(spec, "origin", None)
    try:
        spec_origin_path = Path(spec_origin).resolve() if spec_origin else None
    except (OSError, TypeError, ValueError) as exc:
        raise ImportOriginError("imported OpenCC has an invalid import spec origin") from exc
    if spec_origin_path != origin:
        raise ImportOriginError(
            f"OpenCC import spec origin mismatch: {origin} (spec={spec_origin!r})"
        )
    loader = getattr(spec, "loader", None)
    if isinstance(loader, _SourceOnlyLoader):
        if origin.suffix != ".py":
            raise ImportOriginError(f"source OpenCC module has non-source origin: {origin}")
    elif isinstance(loader, machinery.ExtensionFileLoader):
        if not any(origin.name.endswith(suffix) for suffix in machinery.EXTENSION_SUFFIXES):
            raise ImportOriginError(f"native OpenCC module has unexpected origin: {origin}")
    else:
        raise ImportOriginError(
            f"OpenCC module was loaded by an unapproved loader: {type(loader).__name__}"
        )
    if getattr(loader, "name", None) != getattr(module, "__name__", None):
        raise ImportOriginError("OpenCC module loader name does not match module name")
    locations = getattr(spec, "submodule_search_locations", None)
    if locations is not None:
        for location in locations:
            try:
                location_path = Path(location).resolve()
            except (OSError, TypeError, ValueError) as exc:
                raise ImportOriginError("OpenCC package has an invalid search path") from exc
            if root not in location_path.parents:
                raise ImportOriginError(
                    f"OpenCC package search path escapes selected payload: {location_path}"
                )
    return origin.relative_to(root).as_posix()


def _verify_imported_modules(payload_root: Path) -> None:
    """Verify every OpenCC module loaded by the strict payload import."""

    for name, module in tuple(sys.modules.items()):
        if not _is_opencc_module_name(name):
            continue
        if not isinstance(module, ModuleType):
            raise ImportOriginError(f"OpenCC module entry is not a module: {name}")
        if getattr(module, "__name__", None) != name:
            raise ImportOriginError(f"OpenCC module name mismatch: {name}")
        _verified_module_origin(module, payload_root)


def _can_reuse_verified_modules(payload_root: Path) -> bool:
    """Return whether all currently cached OpenCC modules were verified here."""

    if "opencc" not in sys.modules:
        return False
    modules = [
        (name, module)
        for name, module in tuple(sys.modules.items())
        if _is_opencc_module_name(name)
    ]
    try:
        _verify_imported_modules(payload_root)
    except ImportOriginError:
        return False
    return all(_VERIFIED_MODULES.get(module) == payload_root.resolve() for _, module in modules)


def _remember_verified_modules(payload_root: Path) -> None:
    root = payload_root.resolve()
    for name, module in tuple(sys.modules.items()):
        if _is_opencc_module_name(name) and isinstance(module, ModuleType):
            _VERIFIED_MODULES[module] = root


def _purge_opencc_modules() -> None:
    """Remove stale OpenCC modules before establishing fresh provenance."""

    for name in tuple(sys.modules):
        if _is_opencc_module_name(name) or name == "opencc_clib":
            sys.modules.pop(name, None)


def _remove_payload_finder(finder: "_PayloadImportFinder") -> None:
    try:
        sys.meta_path.remove(finder)
    except ValueError:
        pass


def _remove_payload_finders() -> None:
    for finder in tuple(sys.meta_path):
        if isinstance(finder, _PayloadImportFinder):
            _remove_payload_finder(finder)


def _is_opencc_module_name(name: object) -> bool:
    return isinstance(name, str) and (name == "opencc" or name.startswith("opencc."))


class _SourceOnlyLoader(importlib_abc.Loader):
    """Compile a vendored source file directly, without reading ``__pycache__``."""

    def __init__(
        self,
        fullname: str,
        source_path: Path,
        payload_root: Path,
        verify_payload: Callable[[], object],
        *,
        fail_closed: bool = False,
    ) -> None:
        self.name = fullname
        self.source_path = source_path
        self.payload_root = payload_root.resolve()
        self._verify_payload = verify_payload
        self._fail_closed = fail_closed

    def create_module(self, spec: object) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        self._verify_payload()
        try:
            source = self.source_path.read_bytes()
            code = compile(source, str(self.source_path), "exec", dont_inherit=True)
            # The custom loader never writes or reads a cache.  Clearing this
            # attribute also prevents later code from mistaking the module for a
            # normal cache-backed source import.
            module.__cached__ = None
            exec(code, module.__dict__)
        except Exception as exc:
            if self._fail_closed:
                raise PayloadIntegrityError(
                    f"required OpenCC package failed during import: {self.source_path}"
                ) from exc
            raise
        _VERIFIED_MODULES[module] = self.payload_root


class _BlockedImportLoader(importlib_abc.Loader):
    """Stop PathFinder from accepting an unchecked OpenCC bytecode fallback."""

    def __init__(self, fullname: str) -> None:
        self.name = fullname

    def create_module(self, spec: object) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        raise ImportError(f"unapproved OpenCC module path: {self.name}")


class _VerifiedExtensionLoader(machinery.ExtensionFileLoader):
    """Keep the native loader while rechecking payload bytes before execution."""

    def __init__(
        self,
        fullname: str,
        extension_path: Path,
        payload_root: Path,
        verify_payload: Callable[[], object],
    ) -> None:
        super().__init__(fullname, str(extension_path))
        self.payload_root = payload_root.resolve()
        self._verify_payload = verify_payload

    def create_module(self, spec: object) -> Optional[ModuleType]:
        self._verify_payload()
        try:
            return super().create_module(spec)
        except PayloadIntegrityError:
            raise
        except Exception as exc:
            raise PayloadIntegrityError(
                f"required OpenCC native module failed to initialize: {self.path}"
            ) from exc

    def exec_module(self, module: ModuleType) -> None:
        self._verify_payload()
        try:
            super().exec_module(module)
        except PayloadIntegrityError:
            raise
        except Exception as exc:
            raise PayloadIntegrityError(
                f"required OpenCC native module failed to load: {self.path}"
            ) from exc
        _VERIFIED_MODULES[module] = self.payload_root


class _PayloadImportFinder(importlib_abc.MetaPathFinder):
    """Find only source/native modules in one already-verified payload root."""

    def __init__(self, payload_root: Path, payload_sha256: str) -> None:
        self.payload_root = payload_root.resolve()
        self.package_root = self.payload_root / "opencc"
        self.payload_sha256 = payload_sha256

    def _verify_payload(self) -> None:
        verify_tree_sha256(self.payload_root, self.payload_sha256)

    def find_spec(
        self,
        fullname: str,
        path: Optional[object] = None,
        target: Optional[ModuleType] = None,
    ) -> Optional[object]:
        # The official package tries a historical top-level extension import
        # before its package-relative import.  Block that global fallback so a
        # host-installed opencc_clib can never satisfy the vendored package.
        if fullname == "opencc_clib":
            return _blocked_spec(fullname)
        if not _is_opencc_module_name(fullname):
            return None
        parts = fullname.split(".")
        if any(part.casefold() == "__pycache__" for part in parts[1:]):
            return _blocked_spec(fullname)
        candidate = self.package_root.joinpath(*parts[1:])
        if not _is_within(self.payload_root, candidate):
            if fullname in _REQUIRED_OPENCC_MODULES:
                return _integrity_failure_spec(
                    fullname,
                    f"required OpenCC module escapes selected payload: {candidate}",
                )
            return _blocked_spec(fullname)

        source_path = candidate / "__init__.py" if candidate.is_dir() else candidate.with_suffix(".py")
        if source_path.is_file() and _is_within(self.payload_root, source_path):
            loader = _SourceOnlyLoader(
                fullname,
                source_path,
                self.payload_root,
                self._verify_payload,
                fail_closed=fullname == "opencc.clib",
            )
            search_locations = [str(candidate)] if candidate.is_dir() else None
            spec = spec_from_file_location(
                fullname,
                str(source_path),
                loader=loader,
                submodule_search_locations=search_locations,
            )
            # ``spec_from_file_location`` normally derives a pyc location;
            # source-only imports deliberately have no cache location.
            spec.cached = None
            return spec

        extension_path = _extension_path(candidate)
        if extension_path is not None:
            if not _is_within(self.payload_root, extension_path):
                return _integrity_failure_spec(
                    fullname,
                    f"required OpenCC native module escapes selected payload: {extension_path}",
                )
            loader = _VerifiedExtensionLoader(
                fullname,
                extension_path,
                self.payload_root,
                self._verify_payload,
            )
            spec = spec_from_file_location(fullname, str(extension_path), loader=loader)
            if spec is None:
                return _integrity_failure_spec(
                    fullname,
                    f"required OpenCC native module has no import spec: {extension_path}",
                )
            return spec

        if fullname in _REQUIRED_OPENCC_MODULES:
            return _integrity_failure_spec(
                fullname,
                f"required OpenCC module is missing from selected payload: {candidate}",
            )

        # Returning a blocking spec, instead of None, prevents PathFinder from
        # discovering an otherwise sourceless .pyc under the package path.
        return _blocked_spec(fullname)


def _blocked_spec(fullname: str) -> machinery.ModuleSpec:
    return machinery.ModuleSpec(fullname, _BlockedImportLoader(fullname), origin="blocked")


class _IntegrityFailureLoader(importlib_abc.Loader):
    """Raise a project-owned error before official fallback code can run."""

    def __init__(self, fullname: str, message: str) -> None:
        self.name = fullname
        self._message = message

    def create_module(self, spec: object) -> None:
        raise PayloadIntegrityError(self._message)

    def exec_module(self, module: ModuleType) -> None:
        raise PayloadIntegrityError(self._message)


def _integrity_failure_spec(fullname: str, message: str) -> machinery.ModuleSpec:
    return machinery.ModuleSpec(
        fullname,
        _IntegrityFailureLoader(fullname, message),
        origin="invalid",
    )


_REQUIRED_OPENCC_MODULES = {"opencc.clib", "opencc.clib.opencc_clib"}


def _extension_path(stem: Path) -> Optional[Path]:
    for suffix in machinery.EXTENSION_SUFFIXES:
        candidate = stem.parent / (stem.name + suffix)
        if candidate.is_file():
            return candidate
    return None


def _is_within(root: Path, candidate: Path) -> bool:
    root = root.resolve()
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        return False
    return True


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

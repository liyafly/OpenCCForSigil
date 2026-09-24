"""Machine-readable official wheel payload manifest."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from opencc_backend.errors import ManifestError, RuntimeSelectionError


_SUPPORTED_PLATFORM_ARCHITECTURES = {
    ("linux", "aarch64"),
    ("linux", "x86_64"),
    ("macos", "arm64"),
    ("macos", "x86_64"),
    ("windows", "x86_64"),
}
_SUPPORTED_RUNTIME_IDENTITIES = {
    ("CPython", 3, 14, "cp314", "linux", "aarch64"),
    ("CPython", 3, 14, "cp314", "linux", "x86_64"),
    ("CPython", 3, 14, "cp314", "macos", "arm64"),
    ("CPython", 3, 14, "cp314", "macos", "x86_64"),
    ("CPython", 3, 14, "cp314", "windows", "x86_64"),
    ("CPython", 3, 12, "cp312", "linux", "x86_64"),
}


def _payload_identifier(payload_path: str) -> str:
    prefix = "payloads/"
    if not payload_path.startswith(prefix):
        raise ManifestError(f"manifest payload_path must start with {prefix!r}")
    identifier = payload_path[len(prefix) :]
    if not identifier or "/" in identifier or "\\" in identifier or identifier in {".", ".."}:
        raise ManifestError("manifest payload_path must contain exactly one payload id")
    return identifier


@dataclass(frozen=True)
class NativePluginRecord:
    """One manifest-approved native OpenCC plugin inside a wheel payload."""

    name: str
    kind: str
    upstream_version: str
    upstream_tag: str
    upstream_commit: str
    plugin_dir: str
    library_path: str
    library_sha256: str
    config_names: Tuple[str, ...]
    resource_hashes: Mapping[str, str]
    resource_manifest_sha256: str
    build_profile: str

    @classmethod
    def from_mapping(cls, name: str, value: Mapping[str, Any]) -> "NativePluginRecord":
        required = (
            "kind",
            "upstream_version",
            "upstream_tag",
            "upstream_commit",
            "plugin_dir",
            "library_path",
            "library_sha256",
            "config_names",
            "resource_hashes",
            "resource_manifest_sha256",
            "build_profile",
        )
        missing = [key for key in required if not value.get(key)]
        if missing:
            raise ManifestError(f"native plugin {name!r} missing keys: {', '.join(missing)}")
        config_names = value.get("config_names")
        if not isinstance(config_names, list) or not all(isinstance(item, str) for item in config_names):
            raise ManifestError(f"native plugin {name!r} config_names must be a string list")
        resource_hashes = value.get("resource_hashes")
        if not isinstance(resource_hashes, dict) or not all(
            isinstance(key, str) and isinstance(digest, str)
            for key, digest in resource_hashes.items()
        ):
            raise ManifestError(f"native plugin {name!r} resource_hashes must be an object")
        return cls(
            name=name,
            kind=str(value["kind"]),
            upstream_version=str(value["upstream_version"]),
            upstream_tag=str(value["upstream_tag"]),
            upstream_commit=str(value["upstream_commit"]),
            plugin_dir=str(value["plugin_dir"]),
            library_path=str(value["library_path"]),
            library_sha256=str(value["library_sha256"]),
            config_names=tuple(config_names),
            resource_hashes=dict(resource_hashes),
            resource_manifest_sha256=str(value["resource_manifest_sha256"]),
            build_profile=str(value["build_profile"]),
        )


@dataclass(frozen=True)
class RuntimeKey:
    python_implementation: str
    python_major: int
    python_minor: int
    python_abi: str
    os: str
    architecture: str

    @property
    def python_version(self) -> str:
        return f"{self.python_major}.{self.python_minor}"

    @property
    def payload_id(self) -> str:
        return f"{self.os}-{self.architecture}-{self.python_abi}"


@dataclass(frozen=True)
class PayloadRecord:
    runtime: RuntimeKey
    wheel_name: str
    wheel_sha256: str
    payload_path: str
    payload_sha256: str
    config_hashes: Mapping[str, str]
    config_data: Mapping[str, Any]
    native_plugins: Mapping[str, NativePluginRecord]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PayloadRecord":
        required = (
            "python_implementation",
            "python_version",
            "python_abi",
            "os",
            "architecture",
            "wheel_name",
            "wheel_sha256",
            "payload_path",
            "payload_sha256",
        )
        missing = [key for key in required if not value.get(key)]
        if missing:
            raise ManifestError("payload missing keys: " + ", ".join(missing))
        try:
            major_text, minor_text = str(value["python_version"]).split(".", 1)
            runtime = RuntimeKey(
                python_implementation=str(value["python_implementation"]),
                python_major=int(major_text),
                python_minor=int(minor_text),
                python_abi=str(value["python_abi"]),
                os=str(value["os"]),
                architecture=str(value["architecture"]),
            )
        except (TypeError, ValueError) as exc:
            raise ManifestError("invalid payload runtime fields") from exc
        if not isinstance(value.get("config_hashes", {}), dict):
            raise ManifestError("payload config_hashes must be an object")
        config_data = value.get("config_data", {})
        if not isinstance(config_data, dict):
            raise ManifestError("payload config_data must be an object")
        native_plugins_raw = value.get("native_plugins", {})
        if not isinstance(native_plugins_raw, dict):
            raise ManifestError("payload native_plugins must be an object")
        native_plugins = {
            str(name): NativePluginRecord.from_mapping(str(name), record)
            for name, record in native_plugins_raw.items()
            if isinstance(record, dict)
        }
        if len(native_plugins) != len(native_plugins_raw):
            raise ManifestError("payload native_plugins entries must be objects")
        return cls(
            runtime=runtime,
            wheel_name=str(value["wheel_name"]),
            wheel_sha256=str(value["wheel_sha256"]),
            payload_path=str(value["payload_path"]),
            payload_sha256=str(value["payload_sha256"]),
            config_hashes=dict(value.get("config_hashes", {})),
            config_data=dict(config_data),
            native_plugins=native_plugins,
        )


@dataclass(frozen=True)
class VendorManifest:
    path: Path
    schema_version: int
    opencc_version: str
    distribution_name: str
    import_name: str
    upstream_tag: str
    upstream_commit: str
    tofu_policy: str
    provenance_source: str
    payloads: Tuple[PayloadRecord, ...]
    config_data: Mapping[str, Any]
    python_compatibility: Mapping[str, Any]
    package_flavor: str
    package_runtimes: Tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "VendorManifest":
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            raise ManifestError(f"cannot read vendor manifest: {path}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ManifestError("unsupported or malformed vendor manifest schema")
        payloads_raw = raw.get("payloads")
        if not isinstance(payloads_raw, list):
            raise ManifestError("vendor manifest payloads must be a list")
        payloads = tuple(PayloadRecord.from_mapping(item) for item in payloads_raw)
        payload_ids = tuple(sorted(_payload_identifier(payload.payload_path) for payload in payloads))
        package_raw = raw.get("package")
        if package_raw is None:
            package_flavor = "fat"
            package_runtimes = payload_ids
        else:
            if not isinstance(package_raw, dict):
                raise ManifestError("manifest package must be an object")
            package_flavor = package_raw.get("flavor")
            package_runtimes_raw = package_raw.get("runtimes")
            if package_flavor not in {"fat", "platform"}:
                raise ManifestError("manifest package flavor must be 'fat' or 'platform'")
            if not isinstance(package_runtimes_raw, list) or not all(
                isinstance(item, str) for item in package_runtimes_raw
            ):
                raise ManifestError("manifest package runtimes must be a string list")
            package_runtimes = tuple(package_runtimes_raw)
            if package_runtimes != tuple(sorted(set(package_runtimes))):
                raise ManifestError("manifest package runtimes must be unique and sorted")
            if package_runtimes != payload_ids:
                raise ManifestError("manifest package runtimes differ from payload records")
            if not isinstance(package_raw.get("asset_name"), str) or not package_raw["asset_name"]:
                raise ManifestError("manifest package asset_name must be a non-empty string")
            if package_flavor == "platform" and len(payloads) != 1:
                raise ManifestError("platform package manifest must contain exactly one payload")
        required = (
            "opencc_version",
            "distribution_name",
            "import_name",
            "opencc_upstream_tag",
            "opencc_upstream_commit",
            "tofu_policy",
            "provenance_source",
        )
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ManifestError("vendor manifest missing keys: " + ", ".join(missing))
        if raw["distribution_name"].lower() != "opencc" or raw["import_name"] != "opencc":
            raise ManifestError("manifest must describe the official opencc distribution/import")
        config_data = raw.get("config_data", {})
        if not isinstance(config_data, dict):
            raise ManifestError("config_data must be an object")
        python_compatibility = raw.get("python_compatibility")
        if not isinstance(python_compatibility, dict):
            raise ManifestError("python_compatibility must be an object")
        expected_policy = {
            "implementation": "CPython",
            "major": 3,
            "minor": 14,
            "abi": "cp314",
            "production_baseline": "3.14.2",
            "development_ci": "3.14.7",
            "patch_participates_in_payload_selection": False,
            "additional_runtime_identities": [
                ["CPython", "3.12", "cp312", "linux", "x86_64"],
            ],
        }
        if python_compatibility != expected_policy:
            raise ManifestError(
                "manifest Python policy must be CPython 3.14.x/cp314 with "
                "patch-independent payload selection"
            )
        return cls(
            path=path,
            schema_version=1,
            opencc_version=str(raw["opencc_version"]),
            distribution_name=str(raw["distribution_name"]),
            import_name=str(raw["import_name"]),
            upstream_tag=str(raw["opencc_upstream_tag"]),
            upstream_commit=str(raw["opencc_upstream_commit"]),
            tofu_policy=str(raw["tofu_policy"]),
            provenance_source=str(raw["provenance_source"]),
            payloads=payloads,
            config_data=config_data,
            python_compatibility=python_compatibility,
            package_flavor=str(package_flavor),
            package_runtimes=tuple(package_runtimes),
        )

    def select(self, runtime: RuntimeKey) -> PayloadRecord:
        detected = {
            "implementation": runtime.python_implementation,
            "python_version": runtime.python_version,
            "abi": runtime.python_abi,
            "os": runtime.os,
            "architecture": runtime.architecture,
        }
        error_context = {
            "detected": detected,
            "package_flavor": self.package_flavor,
            "package_runtimes": self.package_runtimes,
        }
        if (runtime.os, runtime.architecture) not in _SUPPORTED_PLATFORM_ARCHITECTURES:
            raise RuntimeSelectionError(
                "Unsupported operating system or architecture: "
                f"{runtime.os}/{runtime.architecture}",
                reason="unsupported_platform",
                **error_context,
            )
        identity = (
            runtime.python_implementation,
            runtime.python_major,
            runtime.python_minor,
            runtime.python_abi,
            runtime.os,
            runtime.architecture,
        )
        if identity not in _SUPPORTED_RUNTIME_IDENTITIES:
            raise RuntimeSelectionError(
                "OpenCCForSigil requires a supported exact CPython runtime; "
                f"detected {runtime.python_implementation} {runtime.python_version} "
                f"with ABI {runtime.python_abi}.",
                reason="python_version",
                **error_context,
            )
        for payload in self.payloads:
            if payload.runtime == runtime:
                return payload
        raise RuntimeSelectionError(
            "No OpenCC payload in this package matches "
            f"{runtime.python_implementation} {runtime.python_version} "
            f"{runtime.python_abi} {runtime.os}/{runtime.architecture}.",
            reason="no_payload_in_package",
            **error_context,
        )

    def payload_root(self, payload: PayloadRecord) -> Path:
        relative = Path(payload.payload_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ManifestError("payload_path escapes vendor directory")
        root = (self.path.parent / relative).resolve()
        vendor_root = self.path.parent.resolve()
        if vendor_root not in root.parents:
            raise ManifestError("payload_path escapes vendor directory")
        return root

    def config_hash(self, payload: PayloadRecord, config: str) -> Optional[str]:
        return payload.config_hashes.get(config)

    def native_plugin(self, payload: PayloadRecord, name: str) -> Optional[NativePluginRecord]:
        return payload.native_plugins.get(name)

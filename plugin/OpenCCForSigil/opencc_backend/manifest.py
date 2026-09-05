"""Machine-readable official wheel payload manifest."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from opencc_backend.errors import ManifestError, RuntimeSelectionError


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
        return cls(
            runtime=runtime,
            wheel_name=str(value["wheel_name"]),
            wheel_sha256=str(value["wheel_sha256"]),
            payload_path=str(value["payload_path"]),
            payload_sha256=str(value["payload_sha256"]),
            config_hashes=dict(value.get("config_hashes", {})),
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
        )

    def select(self, runtime: RuntimeKey) -> PayloadRecord:
        if (
            runtime.python_implementation != "CPython"
            or runtime.python_major != 3
            or runtime.python_minor != 14
            or runtime.python_abi != "cp314"
        ):
            raise RuntimeSelectionError(
                "OpenCCForSigil V1 supports only CPython 3.14.x with wheel ABI cp314; "
                "patch versions do not affect payload selection. "
                "Please switch Sigil Plugin Preferences back to Bundled Python."
            )
        for payload in self.payloads:
            if payload.runtime == runtime:
                return payload
        raise RuntimeSelectionError(
            "Unsupported external Python runtime or unavailable bundled payload: no exact "
            "vendored OpenCC payload for "
            f"{runtime.python_implementation} {runtime.python_version} "
            f"{runtime.python_abi} {runtime.os}/{runtime.architecture}; "
            "OpenCCForSigil is built for Sigil's bundled Python runtime. "
            "Please switch Sigil Plugin Preferences back to Bundled Python."
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

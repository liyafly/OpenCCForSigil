"""Official Python Binding provenance snapshots."""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class BackendProvenance:
    backend_name: str = "BYVoid/OpenCC official Python Binding"
    opencc_version: str = "1.4.2"
    opencc_python_binding_version: str = "1.4.2"
    python_implementation: str = ""
    python_version: str = ""
    python_abi: str = ""
    runtime_os: str = ""
    runtime_architecture: str = ""
    upstream_tag: str = "ver.1.4.2"
    upstream_commit: str = "025f371dc76b598d77384fbdab90c937471844d8"
    import_path_id: str = ""
    wheel_filename: str = ""
    wheel_sha256: Optional[str] = None
    payload_sha256: Optional[str] = None
    import_origin: str = ""
    data_manifest_sha256: Optional[str] = None
    config_sha256: Optional[str] = None
    config_name: str = ""
    tofu_policy: str = "native_default_include"

    def as_dict(self) -> Dict[str, object]:
        return {
            "backend_name": self.backend_name,
            "opencc_version": self.opencc_version,
            "opencc_python_binding_version": self.opencc_python_binding_version,
            "python_implementation": self.python_implementation,
            "python_version": self.python_version,
            "python_abi": self.python_abi,
            "runtime_os": self.runtime_os,
            "runtime_architecture": self.runtime_architecture,
            "upstream_tag": self.upstream_tag,
            "upstream_commit": self.upstream_commit,
            "import_path_id": self.import_path_id,
            "wheel_filename": self.wheel_filename,
            "wheel_sha256": self.wheel_sha256,
            "payload_sha256": self.payload_sha256,
            "import_origin": self.import_origin,
            "data_manifest_sha256": self.data_manifest_sha256,
            "config_sha256": self.config_sha256,
            "config_name": self.config_name,
            "tofu_policy": self.tofu_policy,
        }

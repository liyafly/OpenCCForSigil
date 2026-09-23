"""Errors specific to the official Python Binding boundary."""

from typing import Mapping, Sequence

from app.errors import DataIntegrityError, DependencyError, PluginError


class BackendError(PluginError):
    code = "BACKEND_ERROR"


class ManifestError(BackendError):
    code = "MANIFEST_ERROR"


class RuntimeSelectionError(DependencyError):
    code = "RUNTIME_SELECTION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        detected: Mapping[str, str] | None = None,
        package_flavor: str = "fat",
        package_runtimes: Sequence[str] = (),
        reason: str = "unsupported_platform",
    ) -> None:
        if reason not in {"python_version", "no_payload_in_package", "unsupported_platform"}:
            raise ValueError(f"unsupported runtime selection reason: {reason!r}")
        super().__init__(message)
        self.detected = dict(detected or {})
        self.package_flavor = package_flavor
        self.package_runtimes = tuple(str(item) for item in package_runtimes)
        self.reason = reason


class PayloadIntegrityError(DataIntegrityError):
    code = "PAYLOAD_INTEGRITY_ERROR"


class ImportOriginError(BackendError):
    code = "IMPORT_ORIGIN_ERROR"


class BackendConversionError(BackendError):
    code = "BACKEND_CONVERSION_ERROR"

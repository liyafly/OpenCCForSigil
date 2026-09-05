"""Errors specific to the official Python Binding boundary."""

from app.errors import DataIntegrityError, DependencyError, PluginError


class BackendError(PluginError):
    code = "BACKEND_ERROR"


class ManifestError(BackendError):
    code = "MANIFEST_ERROR"


class RuntimeSelectionError(DependencyError):
    code = "RUNTIME_SELECTION_ERROR"


class PayloadIntegrityError(DataIntegrityError):
    code = "PAYLOAD_INTEGRITY_ERROR"


class ImportOriginError(BackendError):
    code = "IMPORT_ORIGIN_ERROR"


class BackendConversionError(BackendError):
    code = "BACKEND_CONVERSION_ERROR"

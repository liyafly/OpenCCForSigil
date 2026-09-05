"""Single source of truth for the plugin version."""

PLUGIN_NAME = "OpenCCForSigil"
PLUGIN_VERSION = "0.1.0"
SUPPORTED_PYTHON_IMPLEMENTATION = "CPython"
SUPPORTED_PYTHON_MAJOR = 3
SUPPORTED_PYTHON_MINOR = 14
PRODUCTION_PYTHON_BASELINE = "3.14.2"
DEVELOPMENT_PYTHON = "3.14.7"


def supports_formal_runtime(implementation: str, version_info: object) -> bool:
    """Return whether the runtime is within the V1 CPython 3.14.x contract."""

    return (
        str(implementation).lower() == SUPPORTED_PYTHON_IMPLEMENTATION.lower()
        and getattr(version_info, "major", None) == SUPPORTED_PYTHON_MAJOR
        and getattr(version_info, "minor", None) == SUPPORTED_PYTHON_MINOR
    )

"""Single source of truth for the plugin version."""

PLUGIN_NAME = "OpenCCForSigil"
PLUGIN_VERSION = "0.2.1"
SUPPORTED_PYTHON_IMPLEMENTATION = "CPython"
SUPPORTED_PYTHON_MAJOR = 3
SUPPORTED_PYTHON_MINORS = frozenset({12, 14})
PRODUCTION_PYTHON_BASELINE = "3.14.2"
DEVELOPMENT_PYTHON = "3.14.7"


def supports_formal_runtime(implementation: str, version_info: object) -> bool:
    """Return whether the CPython minor has an officially supported payload."""

    return (
        str(implementation).lower() == SUPPORTED_PYTHON_IMPLEMENTATION.lower()
        and getattr(version_info, "major", None) == SUPPORTED_PYTHON_MAJOR
        and getattr(version_info, "minor", None) in SUPPORTED_PYTHON_MINORS
    )

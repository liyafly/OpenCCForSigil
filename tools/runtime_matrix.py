"""Supported Sigil runtime identities for the Fat Plugin release."""

from __future__ import annotations

from typing import Mapping


RUNTIME_FIELDS = (
    "python_implementation",
    "python_version",
    "python_abi",
    "os",
    "architecture",
)

SUPPORTED_RUNTIME_IDENTITIES = (
    ("CPython", "3.14", "cp314", "linux", "x86_64"),
    ("CPython", "3.14", "cp314", "macos", "arm64"),
    ("CPython", "3.14", "cp314", "macos", "x86_64"),
    ("CPython", "3.14", "cp314", "windows", "x86_64"),
)


def runtime_identity(record: Mapping[str, object]) -> tuple[object, ...]:
    """Return the fields that identify one exact Python/native payload."""

    return tuple(record.get(field) for field in RUNTIME_FIELDS)


def format_runtime_identity(identity: tuple[object, ...]) -> str:
    return "/".join(str(value) for value in identity)


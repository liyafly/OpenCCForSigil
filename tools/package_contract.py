"""Names and platform metadata shared by plugin packaging and validation."""

from __future__ import annotations

from typing import Mapping, Sequence


_OSLIST_BY_RUNTIME_OS = {"macos": "osx", "linux": "unx", "windows": "win"}
_OSLIST_ORDER = ("osx", "unx", "win")


def payload_id(record: Mapping[str, object]) -> str:
    """Return the manifest payload id, such as ``macos-arm64-cp314``."""

    path = str(record.get("payload_path", ""))
    prefix = "payloads/"
    if not path.startswith(prefix):
        raise ValueError(f"payload_path must start with {prefix!r}: {path!r}")
    identifier = path[len(prefix) :]
    if not identifier or "/" in identifier or "\\" in identifier or identifier in {".", ".."}:
        raise ValueError(f"payload_path does not contain one payload id: {path!r}")
    return identifier


def package_runtime_ids(payloads: Sequence[Mapping[str, object]]) -> list[str]:
    return sorted(payload_id(record) for record in payloads)


def package_oslist(payloads: Sequence[Mapping[str, object]]) -> str:
    values: set[str] = set()
    for record in payloads:
        runtime_os = str(record.get("os", ""))
        try:
            values.add(_OSLIST_BY_RUNTIME_OS[runtime_os])
        except KeyError as exc:
            raise ValueError(f"unsupported runtime OS for Sigil oslist: {runtime_os!r}") from exc
    if not values:
        raise ValueError("package must contain at least one runtime")
    return ",".join(value for value in _OSLIST_ORDER if value in values)


def package_asset_name(version: str, flavor: str, runtime: str | None = None) -> str:
    if flavor == "fat":
        if runtime is not None:
            raise ValueError("Fat package must not select one runtime")
        return f"OpenCCForSigil_{version}.zip"
    if flavor != "platform":
        raise ValueError(f"unsupported package flavor: {flavor!r}")
    if not runtime or not runtime.endswith("-cp314"):
        raise ValueError("platform package requires a cp314 payload id")
    suffix = runtime[: -len("-cp314")]
    return f"OpenCCForSigil_{version}_{suffix}.zip"

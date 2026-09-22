"""Headless service for the plugin's standard/full self-test."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from sigil.storage import UserDataStore


@dataclass(frozen=True)
class SelfTestReport:
    passed: bool
    checks: Mapping[str, bool]
    details: Mapping[str, Any]
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "checks": dict(self.checks),
            "details": dict(self.details),
            "errors": list(self.errors),
        }


def _backend_test(
    factory: Callable[[str], Any], *, include_optional: bool
) -> tuple[bool, Any, str | None]:
    backend = None
    try:
        backend = factory("s2t")
        result = backend.self_test(include_optional=include_optional)
        passed = bool(getattr(result, "passed", False))
        error = getattr(result, "error", None)
        return passed, result, str(error) if error else None
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"
    finally:
        if backend is not None:
            close = getattr(backend, "close", None)
            if callable(close):
                close()


def _writable_directory(path: Path) -> tuple[bool, str | None]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".self-test-", delete=False) as handle:
            handle.write(b"opencc-for-sigil-self-test\n")
            handle.flush()
            os.fsync(handle.fileno())
            marker = Path(handle.name)
        marker.unlink()
        return True, None
    except (OSError, RuntimeError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def run_self_test(
    *,
    backend_factory: Callable[[str], Any] | None = None,
    data_dir: Path | None = None,
    check_metadata_clear: bool = False,
    metadata_clear_check: Callable[[], bool] | None = None,
) -> SelfTestReport:
    """Run backend, storage, and logging checks without opening a book.

    ``backend_factory`` is injectable for headless tests and host-specific
    wiring. The default factory is imported lazily so this service has no
    alternate OpenCC loading path. ``metadata_clear_check`` is optional and is
    called only when explicitly requested by the caller.
    """

    if backend_factory is None:
        from opencc_backend.backend import OpenCCBackend

        backend_factory = OpenCCBackend
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    errors: list[str] = []

    standard_passed, standard_result, standard_error = _backend_test(
        backend_factory, include_optional=False
    )
    checks["backend_standard"] = standard_passed
    if standard_result is not None:
        details["backend_standard"] = dict(getattr(standard_result, "checks", {}))
    if standard_error:
        errors.append(f"backend_standard: {standard_error}")

    full_passed, full_result, full_error = _backend_test(backend_factory, include_optional=True)
    checks["backend_full"] = full_passed
    if full_result is not None:
        details["backend_full"] = dict(getattr(full_result, "checks", {}))
    if full_error:
        errors.append(f"backend_full: {full_error}")

    root = Path(data_dir) if data_dir is not None else None
    if root is None:
        checks["storage"] = False
        checks["logging"] = False
        errors.extend(("storage: data_dir is required", "logging: data_dir is required"))
    else:
        paths = UserDataStore(root).paths
        details["storage_path"] = str(paths.root)
        details["logging_path"] = str(paths.logs)
        storage_ok, storage_error = _writable_directory(paths.root)
        logging_ok, logging_error = _writable_directory(paths.logs)
        checks["storage"] = storage_ok
        checks["logging"] = logging_ok
        if storage_error:
            errors.append(f"storage: {storage_error}")
        if logging_error:
            errors.append(f"logging: {logging_error}")

    if check_metadata_clear:
        if metadata_clear_check is None:
            checks["metadata_clear"] = False
            errors.append("metadata_clear: no check callback was supplied")
        else:
            try:
                checks["metadata_clear"] = bool(metadata_clear_check())
                if not checks["metadata_clear"]:
                    errors.append("metadata_clear: callback reported failure")
            except Exception as exc:
                checks["metadata_clear"] = False
                errors.append(f"metadata_clear: {type(exc).__name__}: {exc}")

    return SelfTestReport(
        passed=all(checks.values()),
        checks=checks,
        details=details,
        errors=tuple(errors),
    )


__all__ = ["SelfTestReport", "run_self_test"]

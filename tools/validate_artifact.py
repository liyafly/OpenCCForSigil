#!/usr/bin/env python3
"""Validate the final plugin ZIP contents and third-party payload notices."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import zipfile

try:
    from runtime_matrix import (
        SUPPORTED_RUNTIME_IDENTITIES,
        format_runtime_identity,
        runtime_identity,
    )
except ModuleNotFoundError:  # Imported as tools.validate_artifact by tests.
    from tools.runtime_matrix import (
        SUPPORTED_RUNTIME_IDENTITIES,
        format_runtime_identity,
        runtime_identity,
    )


ROOT = Path(__file__).resolve().parents[1]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _zip_tree_hash(archive: zipfile.ZipFile, prefix: str) -> str:
    digest = hashlib.sha256()
    files: list[tuple[str, bytes]] = []
    for name in archive.namelist():
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix) :]
        if not relative:
            continue
        if relative.endswith("/"):
            raise SystemExit(f"payload contains an explicit directory entry: {name}")
        files.append((relative, archive.read(name)))
    for relative, value in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value)
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_relative_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or "" in path.parts
    ):
        raise SystemExit(f"unsafe ZIP member name: {name!r}")


def validate(artifact: Path, *, require_runtimes: bool = False) -> None:
    if not artifact.is_file():
        raise SystemExit(f"plugin artifact is missing: {artifact}")
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise SystemExit("plugin artifact contains duplicate ZIP member names")
        for name in names:
            _validate_relative_name(name)
        top_levels = {name.split("/", 1)[0] for name in names if name}
        if top_levels != {"OpenCCForSigil"}:
            raise SystemExit(f"unexpected plugin ZIP top-level entries: {sorted(top_levels)}")
        forbidden = (
            ".pyc",
            "/__pycache__/",
            "/native_build/",
            "/.git/",
            "/dist/",
        )
        bad = [name for name in names if any(token in name for token in forbidden)]
        if bad:
            raise SystemExit("development-only files in plugin artifact: " + ", ".join(bad[:5]))

        required = {
            "OpenCCForSigil/plugin.xml",
            "OpenCCForSigil/plugin.py",
            "OpenCCForSigil/LICENSE",
            "OpenCCForSigil/NOTICE",
            "OpenCCForSigil/resources/third_party/CPPJIEBA_LICENSE",
            "OpenCCForSigil/vendor/opencc/manifest.json",
            "OpenCCForSigil/resources/third_party/THIRD_PARTY_NOTICES.md",
        }
        missing = sorted(required - set(names))
        if missing:
            raise SystemExit("plugin artifact missing required files: " + ", ".join(missing))

        manifest = json.loads(archive.read("OpenCCForSigil/vendor/opencc/manifest.json"))
        payloads = manifest.get("payloads", [])
        if not payloads:
            raise SystemExit("plugin artifact contains no official OpenCC payload")
        identities = {runtime_identity(payload) for payload in payloads}
        if len(identities) != len(payloads):
            raise SystemExit("plugin artifact contains duplicate payload runtime identities")
        if require_runtimes:
            expected = set(SUPPORTED_RUNTIME_IDENTITIES)
            missing = expected - identities
            unexpected = identities - expected
            if missing or unexpected:
                details = []
                if missing:
                    details.append(
                        "missing="
                        + ",".join(
                            format_runtime_identity(item) for item in sorted(missing, key=str)
                        )
                    )
                if unexpected:
                    details.append(
                        "unexpected="
                        + ",".join(
                            format_runtime_identity(item) for item in sorted(unexpected, key=str)
                        )
                    )
                raise SystemExit("plugin artifact runtime matrix mismatch: " + "; ".join(details))

        declared_prefixes: set[str] = set()
        for payload in payloads:
            if payload.get("payload_runtime_test") != "passed":
                raise SystemExit(
                    "plugin artifact contains a payload without target-runtime self-test: "
                    + str(payload.get("payload_path"))
                )
            payload_path = PurePosixPath(str(payload.get("payload_path", "")))
            if payload_path.is_absolute() or ".." in payload_path.parts:
                raise SystemExit(f"manifest payload path is unsafe: {payload_path}")
            prefix = "OpenCCForSigil/vendor/opencc/" + payload_path.as_posix().rstrip("/") + "/"
            if prefix in declared_prefixes:
                raise SystemExit(f"manifest payload path is duplicated: {prefix}")
            declared_prefixes.add(prefix)
            payload_names = [name for name in names if name.startswith(prefix)]
            if not payload_names:
                raise SystemExit(f"manifest payload is absent from plugin artifact: {prefix}")
            if prefix + "opencc/__init__.py" not in names:
                raise SystemExit(f"payload has no official opencc package: {prefix}")
            if not any(name.endswith(".dist-info/licenses/LICENSE") for name in payload_names):
                raise SystemExit(f"OpenCC license is absent from payload: {prefix}")
            if not any(name.endswith(".dist-info/licenses/AUTHORS") for name in payload_names):
                raise SystemExit(f"OpenCC authors notice is absent from payload: {prefix}")
            actual_tree_hash = _zip_tree_hash(archive, prefix)
            expected_tree_hash = str(payload.get("payload_sha256", ""))
            if actual_tree_hash.lower() != expected_tree_hash.lower():
                raise SystemExit(
                    f"payload tree hash mismatch for {prefix}: "
                    f"expected {expected_tree_hash}, got {actual_tree_hash}"
                )

            config_data = payload.get("config_data")
            if not isinstance(config_data, dict) or not isinstance(config_data.get("files"), dict):
                raise SystemExit(f"payload config_data is malformed: {prefix}")
            expected_data = config_data["files"]
            data_prefix = prefix + "opencc/clib/share/opencc/"
            actual_data = {
                name[len(prefix) :]: name
                for name in payload_names
                if name.startswith(data_prefix)
            }
            expected_data_names = set(str(name) for name in expected_data)
            if set(actual_data) != expected_data_names:
                raise SystemExit(f"payload data file set differs from manifest: {prefix}")
            for relative, expected_hash in expected_data.items():
                name = prefix + str(relative)
                actual_hash = _sha256_bytes(archive.read(name))
                if actual_hash.lower() != str(expected_hash).lower():
                    raise SystemExit(f"payload data hash mismatch: {name}")
            native_plugins = payload.get("native_plugins")
            plugin = native_plugins.get("opencc-jieba") if isinstance(native_plugins, dict) else None
            if not isinstance(plugin, dict):
                raise SystemExit(f"official native opencc-jieba record is absent: {prefix}")
            library_path = prefix + str(plugin.get("library_path", ""))
            if not library_path.startswith(prefix) or library_path not in names:
                raise SystemExit(f"native opencc-jieba library is absent: {library_path}")
            expected_library_hash = str(plugin.get("library_sha256", ""))
            actual_library_hash = _sha256_bytes(archive.read(library_path))
            if actual_library_hash.lower() != expected_library_hash.lower():
                raise SystemExit(f"native opencc-jieba library hash mismatch: {library_path}")
            for config in plugin.get("config_names", []):
                config_name = prefix + "opencc/clib/share/opencc/" + str(config) + ".json"
                if config_name not in names:
                    raise SystemExit(f"native opencc-jieba config is absent: {config_name}")
        payload_prefix = "OpenCCForSigil/vendor/opencc/payloads/"
        actual_prefixes = {
            name[: name.index("/", len(payload_prefix)) + 1]
            for name in names
            if name.startswith(payload_prefix) and "/" in name[len(payload_prefix) :]
        }
        if actual_prefixes != declared_prefixes:
            raise SystemExit("plugin artifact contains undeclared or missing payload directories")
    print(f"plugin artifact valid: {artifact}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--require-runtimes",
        action="store_true",
        help="require every supported Fat Plugin runtime identity",
    )
    args = parser.parse_args()
    validate(args.artifact, require_runtimes=args.require_runtimes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

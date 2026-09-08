#!/usr/bin/env python3
"""Validate the final plugin ZIP contents and third-party payload notices."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
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

_PROFILE_REQUIRED_FIELDS = {
    "schema_version",
    "id",
    "conversion",
    "segmentation",
    "scope",
    "attributes",
    "protected_elements",
    "svg_text",
    "mathml",
}
_PROFILE_SCOPES = {"single", "all_xhtml", "spine", "selected"}
_I18N_LANGUAGES = ("en", "zh-Hans", "zh-Hant")
_PLACEHOLDER = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")
_I18N_REQUIRED_KEYS = frozenset(
    {
        "app.title",
        "config.title",
        "config.direction",
        "config.explanation",
        "config.s2t",
        "config.s2tw",
        "config.s2twp",
        "config.s2hk",
        "config.s2hkp",
        "config.t2s",
        "config.tw2s",
        "config.tw2sp",
        "config.hk2s",
        "config.hk2sp",
        "config.t2tw",
        "config.t2hk",
        "config.tw2t",
        "config.hk2t",
        "config.t2jp",
        "config.jp2t",
        "config.jieba",
        "config.jieba_tooltip",
        "config.jieba_available",
        "config.jieba_unavailable",
        "config.continue",
        "common.cancel",
        "scope.title",
        "scope.single",
        "scope.selected",
        "scope.all",
        "scope.choose",
        "scope.selected_count",
        "scope.all_count",
        "scope.ignored_non_xhtml",
        "scope.none",
        "scope.analyze",
        "scope.filter",
        "scope.select_visible",
        "scope.clear_visible",
        "preview.title",
        "preview.summary",
        "preview.accept_this",
        "preview.skip_this",
        "preview.accept_file",
        "preview.skip_file",
        "preview.accept_all",
        "preview.skip_all",
        "preview.apply",
        "preview.incomplete",
        "preview.no_changes",
        "preview.rule",
        "preview.category",
        "preview.risk",
        "preview.before",
        "preview.change",
        "progress.title",
        "progress.status",
        "progress.phase.analyzing",
        "progress.phase.planning",
        "progress.phase.staging",
        "progress.phase.verifying",
        "result.noop",
        "result.skipped",
        "result.done",
        "result.partial",
        "result.cancelled",
        "result.files_one",
        "result.files_many",
        "result.changes_one",
        "result.changes_many",
        "result.not_written_one",
        "result.not_written_many",
        "result.unchanged_one",
        "result.unchanged_many",
        "error.read",
        "error.failed",
        "error.no_config",
        "error.ui_unavailable",
        "error.backend_self_test",
        "error.scope_invalid",
        "error.scope_exactly_one",
        "language.label",
    }
)

_REQUIRED_MEMBERS = {
    "OpenCCForSigil/plugin.xml",
    "OpenCCForSigil/plugin.py",
    "OpenCCForSigil/LICENSE",
    "OpenCCForSigil/NOTICE",
    "OpenCCForSigil/resources/defaults/conservative.json",
    "OpenCCForSigil/resources/i18n/en.json",
    "OpenCCForSigil/resources/i18n/zh-Hans.json",
    "OpenCCForSigil/resources/i18n/zh-Hant.json",
    "OpenCCForSigil/resources/third_party/MARISA_COPYING.md",
    "OpenCCForSigil/resources/third_party/DARTS_CLONE_COPYING.md",
    "OpenCCForSigil/resources/third_party/RAPIDJSON_LICENSE.txt",
    "OpenCCForSigil/resources/third_party/TCLAP_COPYING",
    "OpenCCForSigil/resources/third_party/PYBIND11_LICENSE",
    "OpenCCForSigil/resources/third_party/CPPJIEBA_LICENSE",
    "OpenCCForSigil/vendor/opencc/manifest.json",
    "OpenCCForSigil/resources/third_party/THIRD_PARTY_NOTICES.md",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _zip_tree_hash(archive: zipfile.ZipFile, prefix: str) -> str:
    digest = hashlib.sha256()
    files: list[tuple[str, str]] = []
    for name in archive.namelist():
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix) :]
        if not relative:
            continue
        if relative.endswith("/"):
            raise SystemExit(f"payload contains an explicit directory entry: {name}")
        files.append((relative, name))
    for relative, name in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with archive.open(name) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _read_json_member(archive: zipfile.ZipFile, name: str) -> object:
    try:
        return json.loads(archive.read(name).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"invalid JSON resource: {name}") from exc


def _validate_profile(profile: object, name: str) -> None:
    if not isinstance(profile, dict):
        raise SystemExit(f"profile resource must be a JSON object: {name}")
    missing = sorted(_PROFILE_REQUIRED_FIELDS - set(profile))
    if missing:
        raise SystemExit(f"profile resource missing keys ({name}): {', '.join(missing)}")
    if not isinstance(profile["id"], str) or not profile["id"]:
        raise SystemExit(f"profile resource has an invalid id: {name}")
    if profile["schema_version"] != 1:
        raise SystemExit(f"profile resource has an unsupported schema version: {name}")
    if not isinstance(profile["conversion"], str) or not profile["conversion"]:
        raise SystemExit(f"profile resource has an invalid conversion: {name}")
    if not isinstance(profile["segmentation"], str) or profile["segmentation"] not in {
        "mmseg",
        "jieba",
    }:
        raise SystemExit(f"profile resource has an invalid segmentation: {name}")
    if not isinstance(profile["scope"], str) or profile["scope"] not in _PROFILE_SCOPES:
        raise SystemExit(f"profile resource has an invalid scope: {name}")
    for key in ("attributes", "protected_elements"):
        value = profile[key]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise SystemExit(f"profile resource has an invalid {key}: {name}")
    for key in ("svg_text", "mathml"):
        if not isinstance(profile[key], bool):
            raise SystemExit(f"profile resource has an invalid {key}: {name}")


def _validate_i18n(catalogs: dict[str, object], names: dict[str, str]) -> None:
    parsed: dict[str, dict[str, str]] = {}
    for language in _I18N_LANGUAGES:
        name = names[language]
        catalog = catalogs[language]
        if not isinstance(catalog, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in catalog.items()
        ):
            raise SystemExit(f"i18n resource must map string keys to string values: {name}")
        parsed[language] = catalog
    expected_keys = set(parsed["en"])
    missing_required = sorted(_I18N_REQUIRED_KEYS - expected_keys)
    if missing_required:
        raise SystemExit(
            "i18n resource is missing required runtime keys from en: "
            + ", ".join(missing_required)
        )
    for language, catalog in parsed.items():
        if set(catalog) != expected_keys:
            raise SystemExit(f"i18n resource keys differ from en: {names[language]}")
        for key in expected_keys:
            expected = set(_PLACEHOLDER.findall(parsed["en"][key]))
            actual = set(_PLACEHOLDER.findall(catalog[key]))
            if actual != expected:
                raise SystemExit(f"i18n resource placeholders differ: {names[language]}:{key}")


def _validate_runtime_resources(archive: zipfile.ZipFile) -> None:
    profile_name = "OpenCCForSigil/resources/defaults/conservative.json"
    _validate_profile(_read_json_member(archive, profile_name), profile_name)
    catalogs = {}
    names = {}
    for language in _I18N_LANGUAGES:
        name = f"OpenCCForSigil/resources/i18n/{language}.json"
        names[language] = name
        catalogs[language] = _read_json_member(archive, name)
    _validate_i18n(catalogs, names)


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
            "/native_build/",
            "/.git/",
            "/dist/",
        )
        bad = [
            name
            for name in names
            if PurePosixPath(name).suffix.lower() in {".pyc", ".pyo"}
            or "__pycache__" in PurePosixPath(name).parts
            or any(token in name for token in forbidden)
        ]
        if bad:
            raise SystemExit("development-only files in plugin artifact: " + ", ".join(bad[:5]))

        missing = sorted(_REQUIRED_MEMBERS - set(names))
        if missing:
            raise SystemExit("plugin artifact missing required files: " + ", ".join(missing))
        _validate_runtime_resources(archive)

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

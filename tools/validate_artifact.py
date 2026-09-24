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
import xml.etree.ElementTree as ET

try:
    from package_contract import package_asset_name, package_oslist, package_runtime_ids
    from runtime_matrix import (
        SUPPORTED_RUNTIME_IDENTITIES,
        format_runtime_identity,
        runtime_identity,
    )
    from native_compatibility import NativeCompatibilityError, validate_binary_bytes
    from runtime_subset import RuntimeSubsetError, validate_derivation
except ModuleNotFoundError:  # Imported as tools.validate_artifact by tests.
    from tools.package_contract import package_asset_name, package_oslist, package_runtime_ids
    from tools.runtime_matrix import (
        SUPPORTED_RUNTIME_IDENTITIES,
        format_runtime_identity,
        runtime_identity,
    )
    from tools.native_compatibility import NativeCompatibilityError, validate_binary_bytes
    from tools.runtime_subset import RuntimeSubsetError, validate_derivation


ROOT = Path(__file__).resolve().parents[1]
MAX_PLATFORM_ARTIFACT_SIZE_BYTES = 7_000_000
MAX_FIRST_STAGE_FAT_ARTIFACT_SIZE_BYTES = 30_000_000
MAX_THIRD_STAGE_FAT_ARTIFACT_SIZE_BYTES = 12_000_000

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
        "recovery.preferences_corrupt",
        "recovery.preferences_future_schema",
        "recovery.profile_recovered",
        "recovery.rulesets_missing",
        "recovery.generic",
        "scope.title",
        "scope.single",
        "scope.selected",
        "scope.all",
        "scope.selection_count",
        "scope.selection_guide",
        "scope.navigation_suffix",
        "scope.ignored_non_xhtml",
        "scope.none",
        "scope.analyze",
        "scope.back",
        "scope.checkpoint_notice",
        "scope.checkpoint_hide",
        "scope.checkpoint_close",
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
        "preview.discard_title",
        "preview.discard_message",
        "preview.discard_yes",
        "preview.discard_no",
        "preview.checkpoint_confirm",
        "preview.checkpoint_confirm_yes",
        "preview.checkpoint_confirm_back",
        "preview.incomplete",
        "preview.no_changes",
        "preview.rule",
        "preview.category",
        "preview.risk",
        "preview.column.status",
        "preview.column.file",
        "preview.column.source",
        "preview.column.target",
        "preview.column.category",
        "preview.column.risk",
        "preview.status.accepted",
        "preview.status.skipped",
        "preview.status.pending",
        "preview.filter_file_option",
        "preview.file.metadata",
        "preview.show_source_context",
        "preview.group_row_marker",
        "preview.group_explanation",
        "preview.group_prompt",
        "preview.accept_language_group",
        "preview.skip_language_group",
        "preview.group_accepted",
        "preview.group_skipped",
        "preview.before",
        "preview.after",
        "preview.category_value.character",
        "preview.category_value.phrase",
        "preview.category_value.regional",
        "preview.category_value.variant",
        "preview.category_value.quotation",
        "preview.category_value.user_rule",
        "preview.category_value.language_metadata",
        "preview.category_value.numeric_reference",
        "preview.category_value.opencc_change",
        "preview.category_value.punctuation",
        "preview.risk_value.low",
        "preview.risk_value.review",
        "preview.risk_value.high",
        "progress.title",
        "result.title",
        "progress.status",
        "progress.phase.analyzing",
        "progress.phase.planning",
        "progress.phase.staging",
        "progress.phase.verifying",
        "progress.phase.rechecking",
        "progress.phase.committing",
        "result.back_to_scope",
        "result.invalid_sources",
        "result.files_all_skipped",
        "error.no_config",
        "a11y.scope.information",
        "error.ui_unavailable",
        "error.scope_exactly_one",
        "language.label",
        "options.documents",
        "options.advanced",
        "options.attributes",
        "options.content",
        "options.punctuation",
        "options.language_tags",
        "options.diagnostics",
        "options.high_risk",
        "options.active_rulesets",
        "options.nav_unavailable",
        "settings.tools",
        "settings.self_test_check",
        "settings.self_test_result",
        "settings.self_test_copy",
        "settings.self_test_details",
        "settings.self_test_passed",
        "settings.self_test_failed",
        "history.title",
        "history.date",
        "history.file",
        "history.profile",
        "history.direction",
        "history.files",
        "history.changes",
        "history.status",
        "history.open",
        "history.export",
        "history.close",
        "history.none",
        "history.corrupt",
        "history.select",
        "history.backup_rebuild",
        "history.rebuilt",
        "history.cleanup",
        "history.cleanup_prompt",
        "history.cleanup_done",
        "history.empty_value",
        "history.status.success",
        "history.status.completed",
        "history.status.partial_failure",
        "history.status.failed",
        "history.status.cancelled",
        "result.row.scanned",
        "result.row.written",
        "result.row.unwritten",
        "result.status.success",
        "result.status.partial",
        "result.status.cancelled",
        "result.status.skipped",
        "result.status.noop",
        "result.save_reminder",
        "result.view_report",
    }
)

_I18N_REQUIRED_KEYS = _I18N_REQUIRED_KEYS | frozenset(
    {
        'diagnostic.inline_boundary',
        'diagnostic.mixed_script',
        'diagnostic.quote_unbalanced',
        'diagnostic.source_invalid_xhtml',
        'diagnostic.unknown',
        'preview.accept_filter',
        'preview.back_settings',
        'preview.checkpoint_hide',
        'preview.checkpoint_title',
        'preview.diagnostic_detail',
        'preview.diagnostics',
        'preview.invalid_source_location',
        'preview.skipped_sources',
        'preview.export',
        'preview.export_full_diff',
        'preview.filter_all',
        'preview.filter_category',
        'preview.filter_file',
        'preview.filter_risk',
        'preview.skip_filter',
        'profile.ask_name',
        'profile.close',
        'profile.config_unavailable',
        'profile.confirm_delete',
        'profile.conversion',
        'profile.copied',
        'profile.copy',
        'profile.delete',
        'profile.delete_modified',
        'profile.duplicate_name',
        'profile.from_current',
        'profile.invalid_name',
        'profile.not_selected',
        'profile.operation_failed',
        'profile.options',
        'profile.rename',
        'profile.rules',
        'profile.skipped_files',
        'profile.summary',
        'profile.title',
        'profile.unavailable',
        'profile.use',
        'rules.add',
        'rules.apply',
        'rules.attribution_label',
        'rules.cancel',
        'rules.close',
        'rules.config_label',
        'rules.conflict.DIRECTION_OVERLAP',
        'rules.conflict.DUPLICATE',
        'rules.conflict.PROTECTED_CONFLICT',
        'rules.conflict.SAME_SOURCE_DIFFERENT_TARGET',
        'rules.conflict.unknown',
        'rules.direction',
        'rules.duplicate_ruleset',
        'rules.editor_group',
        'rules.exact',
        'rules.export',
        'rules.field.book_fingerprint',
        'rules.field.comment',
        'rules.field.direction',
        'rules.field.enabled',
        'rules.field.id',
        'rules.field.priority',
        'rules.field.profile_id',
        'rules.field.scope',
        'rules.field.source',
        'rules.field.source_note',
        'rules.field.target',
        'rules.field.type',
        'rules.final_label',
        'rules.hits_label',
        'rules.import',
        'rules.import_add',
        'rules.import_cancel',
        'rules.import_format',
        'rules.import_line',
        'rules.import_summary',
        'rules.input',
        'rules.input_label',
        'rules.input_required',
        'rules.inspect',
        'rules.inspector_title',
        'rules.invalid_ruleset',
        'rules.new_ruleset',
        'rules.no_converter',
        'rules.no_hits',
        'rules.opencc_label',
        'rules.operation_failed',
        'rules.original_label',
        'rules.output',
        'rules.post_rules_label',
        'rules.pre_rules_label',
        'rules.priority',
        'rules.protect',
        'rules.remove',
        'rules.rename_ruleset',
        'rules.rule_hit',
        'rules.ruleset',
        'rules.scope',
        'rules.scope_book',
        'rules.scope_global',
        'rules.scope_profile',
        'rules.skip_invalid',
        'rules.skipped_files',
        'rules.source',
        'rules.target',
        'rules.test',
        'rules.test_group',
        'rules.title',
        'rules.transfer_group',
        'rules.type',
        'rules.update',
        'rules.validation.field',
        'rules.validation.generic',
        'rules.validation.row',
        'rules.validation.row_field',
        'rules.validation.unknown_field',
    }
)
_I18N_REQUIRED_KEYS = _I18N_REQUIRED_KEYS | frozenset(
    {
        "common.no",
        "common.yes",
        "config.jieba_combination",
        "options.current_profile",
        "options.profile_modified",
        "preview.apply_decisions",
        "preview.apply_decisions_many",
        "preview.apply_decisions_one",
        "preview.apply_no_changes",
        "preview.apply_status_none",
        "preview.apply_status_pending",
        "preview.apply_status_ready",
        "preview.file_count_many",
        "preview.file_count_one",
        "profile.default_name",
        "profile.disabled",
        "profile.enabled",
        "profile.status",
        "profile.summary_option",
        "rules.attribution_opencc",
        "rules.attribution_user",
        "rules.category_unknown",
        "rules.classification",
        "rules.confidence.high",
        "rules.confidence.low",
        "rules.confidence.medium",
        "rules.export_default_filename",
        "rules.export_filter",
        "rules.import_filter",
        "rules.matched_user_rules",
        "common.label_separator",
    }
)
_I18N_CATALOG = json.loads(
    (ROOT / "plugin/OpenCCForSigil/resources/i18n/en.json").read_text(encoding="utf-8")
)
_I18N_REQUIRED_KEYS = _I18N_REQUIRED_KEYS | frozenset(
    key for key in _I18N_CATALOG
    if key.startswith(("error.", "settings."))
)
_I18N_REQUIRED_KEYS = _I18N_REQUIRED_KEYS | frozenset(
    {
        "common.error_details",
        "language.name.en",
        "language.name.zh-Hans",
        "language.name.zh-Hant",
        "options.force_pivot_mismatch",
        "options.invalid",
        "options.region_required",
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


def _validate_package_contract(
    archive: zipfile.ZipFile,
    manifest: dict[str, object],
    *,
    requested_flavor: str | None,
    runtime: str | None,
) -> str:
    package = manifest.get("package")
    if not isinstance(package, dict) or package.get("flavor") not in {"fat", "platform"}:
        raise SystemExit("plugin artifact package metadata must declare flavor 'fat' or 'platform'")
    flavor = str(package["flavor"])
    if requested_flavor is not None and flavor != requested_flavor:
        raise SystemExit(
            f"plugin artifact package flavor mismatch: expected {requested_flavor}, got {flavor}"
        )
    if runtime is not None and flavor != "platform":
        raise SystemExit("--runtime is only valid for a platform package")
    if flavor == "platform" and requested_flavor == "platform" and runtime is None:
        raise SystemExit("--runtime is required to validate a platform package")

    payloads = manifest.get("payloads")
    if not isinstance(payloads, list) or not payloads or not all(
        isinstance(record, dict) for record in payloads
    ):
        raise SystemExit("plugin artifact contains no valid runtime payload records")
    records = [record for record in payloads if isinstance(record, dict)]
    try:
        runtime_ids = package_runtime_ids(records)
        expected_oslist = package_oslist(records)
    except ValueError as exc:
        raise SystemExit(f"plugin artifact runtime metadata is invalid: {exc}") from exc
    if len(runtime_ids) != len(set(runtime_ids)):
        raise SystemExit("plugin artifact contains duplicate payload ids")
    declared_runtimes = package.get("runtimes")
    if declared_runtimes != runtime_ids:
        raise SystemExit("plugin artifact package.runtimes differs from manifest payloads")
    if flavor == "platform":
        if len(records) != 1:
            raise SystemExit("platform package must contain exactly one manifest payload")
        if runtime is not None and runtime_ids != [runtime]:
            raise SystemExit(
                f"platform package runtime mismatch: expected {runtime}, got {runtime_ids[0]}"
            )
        package_runtime = runtime_ids[0]
    else:
        if runtime is not None:
            raise SystemExit("--runtime is only valid for a platform package")
        package_runtime = None

    plugin_xml_name = "OpenCCForSigil/plugin.xml"
    try:
        plugin_root = ET.fromstring(archive.read(plugin_xml_name))
    except ET.ParseError as exc:
        raise SystemExit(f"plugin artifact plugin.xml is invalid: {exc}") from exc
    if plugin_root.tag != "plugin":
        raise SystemExit("plugin artifact plugin.xml root must be <plugin>")
    version = plugin_root.findtext("version")
    actual_oslist = plugin_root.findtext("oslist")
    if not version:
        raise SystemExit("plugin artifact plugin.xml is missing <version>")
    if actual_oslist != expected_oslist:
        raise SystemExit(
            f"plugin.xml oslist differs from package runtimes: expected {expected_oslist}, got {actual_oslist}"
        )
    try:
        expected_asset = package_asset_name(version, flavor, package_runtime)
    except ValueError as exc:
        raise SystemExit(f"plugin artifact package metadata is invalid: {exc}") from exc
    if package.get("asset_name") != expected_asset:
        raise SystemExit(
            f"plugin artifact package.asset_name differs from contract: expected {expected_asset}"
        )
    return flavor


def validate(
    artifact: Path,
    *,
    require_runtimes: bool = False,
    flavor: str | None = None,
    runtime: str | None = None,
) -> None:
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
        if not isinstance(manifest, dict):
            raise SystemExit("plugin artifact vendor manifest must be an object")
        actual_flavor = _validate_package_contract(
            archive,
            manifest,
            requested_flavor=flavor,
            runtime=runtime,
        )
        size_limit = (
            MAX_PLATFORM_ARTIFACT_SIZE_BYTES
            if actual_flavor == "platform"
            else MAX_FIRST_STAGE_FAT_ARTIFACT_SIZE_BYTES
        )
        if artifact.stat().st_size > size_limit:
            raise SystemExit(
                f"plugin artifact exceeds the {actual_flavor} size budget: "
                f"{artifact.stat().st_size} > {size_limit} bytes"
            )
        payloads = manifest.get("payloads", [])
        if not payloads:
            raise SystemExit("plugin artifact contains no official OpenCC payload")
        identities = {runtime_identity(payload) for payload in payloads}
        if len(identities) != len(payloads):
            raise SystemExit("plugin artifact contains duplicate payload runtime identities")
        if require_runtimes:
            if actual_flavor != "fat":
                raise SystemExit("--require-runtimes is valid only for a Fat package")
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
            native_plugins = payload.get("native_plugins")
            plugin = native_plugins.get("opencc-jieba") if isinstance(native_plugins, dict) else None
            if not isinstance(plugin, dict):
                raise SystemExit(f"official native opencc-jieba record is absent: {prefix}")
            kept_paths = [name[len(prefix) :] for name in payload_names]
            try:
                validate_derivation(
                    payload,
                    kept_paths=kept_paths,
                    plugin_dir=str(plugin.get("plugin_dir", "")),
                    library_path=str(plugin.get("library_path", "")),
                )
            except RuntimeSubsetError as exc:
                raise SystemExit(f"runtime subset validation failed for {prefix}: {exc}") from exc
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
            expected_data_hash = config_data.get("manifest_sha256")
            canonical_data = json.dumps(
                expected_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if hashlib.sha256(canonical_data).hexdigest() != expected_data_hash:
                raise SystemExit(f"payload data manifest hash mismatch: {prefix}")
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
            resources = plugin.get("resource_hashes")
            if not isinstance(resources, dict) or not resources:
                raise SystemExit(f"native opencc-jieba resource hashes are absent: {prefix}")
            expected_resources = {
                data_path
                for data_path in expected_data
                if data_path.startswith("opencc/clib/share/opencc/jieba_dict/")
            }
            expected_resources.update(
                "opencc/clib/share/opencc/" + str(config) + ".json"
                for config in plugin.get("config_names", [])
            )
            if set(resources) != expected_resources:
                raise SystemExit(f"native opencc-jieba resource list differs from subset: {prefix}")
            for relative, expected_hash in resources.items():
                name = prefix + str(relative)
                if name not in names or expected_data.get(str(relative)) != expected_hash:
                    raise SystemExit(f"native opencc-jieba resource is absent or differs: {name}")
                if _sha256_bytes(archive.read(name)).lower() != str(expected_hash).lower():
                    raise SystemExit(f"native opencc-jieba resource hash mismatch: {name}")
            canonical_resources = json.dumps(
                resources, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if hashlib.sha256(canonical_resources).hexdigest() != plugin.get(
                "resource_manifest_sha256"
            ):
                raise SystemExit(f"native opencc-jieba resource manifest hash mismatch: {prefix}")
            library_path = prefix + str(plugin.get("library_path", ""))
            if not library_path.startswith(prefix) or library_path not in names:
                raise SystemExit(f"native opencc-jieba library is absent: {library_path}")
            expected_library_hash = str(plugin.get("library_sha256", ""))
            actual_library_hash = _sha256_bytes(archive.read(library_path))
            if actual_library_hash.lower() != expected_library_hash.lower():
                raise SystemExit(f"native opencc-jieba library hash mismatch: {library_path}")
            try:
                validate_binary_bytes(
                    archive.read(library_path),
                    runtime_os=str(payload.get("os", "")),
                    architecture=str(payload.get("architecture", "")),
                    label=library_path,
                )
            except NativeCompatibilityError as exc:
                raise SystemExit(f"native opencc-jieba binary compatibility check failed: {exc}") from exc
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
    parser.add_argument(
        "--flavor",
        choices=("fat", "platform"),
        help="expected package flavor",
    )
    parser.add_argument(
        "--runtime",
        help="expected payload id for a platform package",
    )
    args = parser.parse_args()
    if args.runtime and args.flavor != "platform":
        parser.error("--runtime requires --flavor platform")
    validate(
        args.artifact,
        require_runtimes=args.require_runtimes,
        flavor=args.flavor,
        runtime=args.runtime,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

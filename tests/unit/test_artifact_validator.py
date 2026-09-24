from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from tools.build_plugin import build
from tools.validate_artifact import (
    _I18N_REQUIRED_KEYS,
    MAX_FIRST_STAGE_FAT_ARTIFACT_SIZE_BYTES,
    MAX_PLATFORM_ARTIFACT_SIZE_BYTES,
    _zip_tree_hash,
    validate as validate_artifact,
)


@pytest.fixture(scope="module")
def artifact(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("artifact") / "plugin.zip")


@pytest.fixture(scope="module")
def platform_artifact(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(
        tmp_path_factory.mktemp("platform-artifact") / "plugin.zip",
        flavor="platform",
        runtime="macos-arm64-cp314",
    )


def _rewrite_archive(source: Path, target: Path, replacements: dict[str, bytes]) -> None:
    with zipfile.ZipFile(source) as source_archive, zipfile.ZipFile(target, "w") as target_archive:
        seen: set[str] = set()
        for info in source_archive.infolist():
            seen.add(info.filename)
            value = replacements.get(info.filename)
            if value is None:
                value = source_archive.read(info.filename)
            target_archive.writestr(info, value)
        for name, value in replacements.items():
            if name in seen:
                continue
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = (
                zipfile.ZIP_STORED if name.endswith("oversized.bin") else zipfile.ZIP_DEFLATED
            )
            target_archive.writestr(info, value)


def test_all_runtime_error_and_settings_keys_are_required_by_artifact_validation():
    catalog = json.loads(Path(
        "plugin/OpenCCForSigil/resources/i18n/en.json").read_text(encoding="utf-8"))
    runtime_keys = {
        key for key in catalog
        if key.startswith(("error.", "settings."))
    } | {
        "diagnostic.source_invalid",
        "options.current_profile",
        "options.profile_modified",
    }

    assert runtime_keys <= _I18N_REQUIRED_KEYS


def _read_member(source: Path, name: str) -> object:
    with zipfile.ZipFile(source) as archive:
        return json.loads(archive.read(name).decode("utf-8"))


@pytest.mark.parametrize(
    "missing_member",
    [
        "OpenCCForSigil/resources/defaults/conservative.json",
        "OpenCCForSigil/resources/i18n/en.json",
        "OpenCCForSigil/resources/i18n/zh-Hans.json",
        "OpenCCForSigil/resources/i18n/zh-Hant.json",
    ],
)
def test_validator_rejects_archive_missing_runtime_resource(
    artifact: Path, tmp_path: Path, missing_member: str
):
    target = tmp_path / "missing.zip"
    with zipfile.ZipFile(artifact) as source_archive, zipfile.ZipFile(target, "w") as target_archive:
        for info in source_archive.infolist():
            if info.filename != missing_member:
                target_archive.writestr(info, source_archive.read(info.filename))

    with pytest.raises(SystemExit, match=missing_member):
        validate_artifact(target)


def test_validator_rejects_corrupt_runtime_json(artifact: Path, tmp_path: Path):
    name = "OpenCCForSigil/resources/i18n/en.json"
    target = tmp_path / "corrupt.zip"
    _rewrite_archive(artifact, target, {name: b"{"})

    with pytest.raises(SystemExit, match="invalid JSON resource.*en\\.json"):
        validate_artifact(target)


def test_validator_rejects_profile_missing_controller_field(artifact: Path, tmp_path: Path):
    name = "OpenCCForSigil/resources/defaults/conservative.json"
    profile = _read_member(artifact, name)
    assert isinstance(profile, dict)
    profile.pop("scope")
    target = tmp_path / "profile-missing.zip"
    _rewrite_archive(artifact, target, {name: json.dumps(profile).encode("utf-8")})

    with pytest.raises(SystemExit, match="profile resource missing keys.*scope"):
        validate_artifact(target)


def test_validator_rejects_i18n_key_mismatch(artifact: Path, tmp_path: Path):
    name = "OpenCCForSigil/resources/i18n/zh-Hans.json"
    catalog = _read_member(artifact, name)
    assert isinstance(catalog, dict)
    catalog.pop("app.title")
    target = tmp_path / "i18n-key-mismatch.zip"
    _rewrite_archive(artifact, target, {name: json.dumps(catalog, ensure_ascii=False).encode("utf-8")})

    with pytest.raises(SystemExit, match="i18n resource keys differ.*zh-Hans"):
        validate_artifact(target)


def test_validator_rejects_i18n_placeholder_mismatch(artifact: Path, tmp_path: Path):
    name = "OpenCCForSigil/resources/i18n/zh-Hant.json"
    catalog = _read_member(artifact, name)
    assert isinstance(catalog, dict)
    catalog["scope.selection_count"] = "已選取 {selected} 個 XHTML 檔案"
    target = tmp_path / "i18n-placeholder-mismatch.zip"
    _rewrite_archive(artifact, target, {name: json.dumps(catalog, ensure_ascii=False).encode("utf-8")})

    with pytest.raises(SystemExit, match="i18n resource placeholders differ.*scope.selection_count"):
        validate_artifact(target)


@pytest.mark.parametrize(
    "missing_key",
    (
        "diagnostic.inline_boundary",
        "language.name.en",
        "options.region_required",
        "rules.validation.row_field",
        "common.label_separator",
        "preview.file_count_one",
        "preview.file_count_many",
        "rules.import_filter",
        "rules.export_default_filename",
        "rules.export_filter",
    ),
)
def test_validator_rejects_archive_missing_new_runtime_i18n_key(
    artifact: Path, tmp_path: Path, missing_key: str,
):
    replacements = {}
    for language in ("en", "zh-Hans", "zh-Hant"):
        name = f"OpenCCForSigil/resources/i18n/{language}.json"
        catalog = _read_member(artifact, name)
        catalog.pop(missing_key)
        replacements[name] = json.dumps(catalog, ensure_ascii=False).encode("utf-8")
    target = tmp_path / f"missing-{missing_key.replace('.', '-')}.zip"
    _rewrite_archive(artifact, target, replacements)

    with pytest.raises(SystemExit, match="i18n resource is missing required runtime keys"):
        validate_artifact(target)


def test_validator_rejects_empty_i18n_catalogs_missing_runtime_keys(
    artifact: Path, tmp_path: Path
):
    names = {
        f"OpenCCForSigil/resources/i18n/{language}.json": b"{}"
        for language in ("en", "zh-Hans", "zh-Hant")
    }
    target = tmp_path / "i18n-empty.zip"
    _rewrite_archive(artifact, target, names)

    with pytest.raises(SystemExit, match="i18n resource is missing required runtime keys"):
        validate_artifact(target)


@pytest.mark.parametrize(
    "member",
    [
        "OpenCCForSigil/runtime.pyc",
        "OpenCCForSigil/runtime.pyo",
        "OpenCCForSigil/opencc/__pycache__/cached.py",
    ],
)
def test_validator_rejects_bytecode_members(artifact: Path, tmp_path: Path, member: str):
    target = tmp_path / "bytecode.zip"
    _rewrite_archive(artifact, target, {member: b"not executable"})

    with pytest.raises(SystemExit, match="development-only files.*" + member.replace(".", r"\.")):
        validate_artifact(target)


def test_validator_allows_pyc_substrings_that_are_not_bytecode(artifact: Path, tmp_path: Path):
    member = "OpenCCForSigil/notes/runtime.pyc.bak"
    target = tmp_path / "pyc-substring.zip"
    _rewrite_archive(artifact, target, {member: b"documentation"})

    validate_artifact(target)


@pytest.mark.parametrize(
    "member",
    [
        "OpenCCForSigil/vendor/opencc/payloads/macos-arm64-cp314/opencc/clib/bin/opencc",
        "OpenCCForSigil/vendor/opencc/payloads/macos-arm64-cp314/opencc/clib/lib/libopencc.a",
        "OpenCCForSigil/vendor/opencc/payloads/macos-arm64-cp314/opencc/clib/include/opencc/opencc.h",
        "OpenCCForSigil/vendor/opencc/payloads/macos-arm64-cp314/opencc/clib/share/opencc/jieba_dict/jieba.dict.utf8",
    ],
)
def test_validator_rejects_excluded_wheel_files(
    artifact: Path, tmp_path: Path, member: str
):
    target = tmp_path / "excluded-wheel-file.zip"
    _rewrite_archive(artifact, target, {member: b"excluded"})

    with pytest.raises(SystemExit, match="excluded OpenCC files are present"):
        validate_artifact(target)


@pytest.mark.parametrize(
    ("flavor", "limit"),
    [
        ("platform", MAX_PLATFORM_ARTIFACT_SIZE_BYTES),
        ("fat", MAX_FIRST_STAGE_FAT_ARTIFACT_SIZE_BYTES),
    ],
)
def test_validator_rejects_artifacts_over_size_budget(
    artifact: Path, platform_artifact: Path, tmp_path: Path, flavor: str, limit: int
):
    source = platform_artifact if flavor == "platform" else artifact
    target = tmp_path / f"oversized-{flavor}.zip"
    _rewrite_archive(
        source,
        target,
        {
            "OpenCCForSigil/oversized.bin": bytes(limit + 1),
        },
    )

    with pytest.raises(SystemExit, match=f"exceeds the {flavor} size budget"):
        validate_artifact(target)


def test_platform_validator_rejects_a_second_payload(
    platform_artifact: Path, tmp_path: Path
):
    manifest_name = "OpenCCForSigil/vendor/opencc/manifest.json"
    manifest = _read_member(platform_artifact, manifest_name)
    payload = dict(manifest["payloads"][0])
    payload["os"] = "windows"
    payload["architecture"] = "x86_64"
    payload["payload_path"] = "payloads/windows-x86_64-cp314"
    manifest["payloads"].append(payload)
    manifest["package"]["runtimes"] = [
        "macos-arm64-cp314",
        "windows-x86_64-cp314",
    ]
    target = tmp_path / "platform-with-second-payload.zip"
    _rewrite_archive(
        platform_artifact,
        target,
        {manifest_name: json.dumps(manifest, ensure_ascii=False).encode("utf-8")},
    )

    with pytest.raises(SystemExit, match="platform package must contain exactly one manifest payload"):
        validate_artifact(target, flavor="platform", runtime="macos-arm64-cp314")


def test_platform_validator_rejects_a_wrong_oslist(
    platform_artifact: Path, tmp_path: Path
):
    name = "OpenCCForSigil/plugin.xml"
    with zipfile.ZipFile(platform_artifact) as archive:
        plugin_xml = archive.read(name).decode("utf-8")
    target = tmp_path / "platform-wrong-oslist.zip"
    _rewrite_archive(
        platform_artifact,
        target,
        {name: plugin_xml.replace("<oslist>osx</oslist>", "<oslist>osx,unx,win</oslist>").encode("utf-8")},
    )

    with pytest.raises(SystemExit, match="plugin.xml oslist differs from package runtimes"):
        validate_artifact(target, flavor="platform", runtime="macos-arm64-cp314")


def test_platform_validator_rejects_a_flavor_mismatch(
    platform_artifact: Path, tmp_path: Path
):
    name = "OpenCCForSigil/vendor/opencc/manifest.json"
    manifest = _read_member(platform_artifact, name)
    manifest["package"]["flavor"] = "fat"
    target = tmp_path / "platform-wrong-flavor.zip"
    _rewrite_archive(
        platform_artifact,
        target,
        {name: json.dumps(manifest, ensure_ascii=False).encode("utf-8")},
    )

    with pytest.raises(SystemExit, match="package flavor mismatch: expected platform, got fat"):
        validate_artifact(target, flavor="platform", runtime="macos-arm64-cp314")


class _ChunkedReader(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("tree hash must read archive members in chunks")
        return super().read(min(size, 3))


class _StreamingArchive:
    def __init__(self, members: dict[str, bytes]):
        self.members = members

    def namelist(self) -> list[str]:
        return list(self.members)

    def read(self, name: str) -> bytes:
        raise AssertionError(f"tree hash must not use archive.read({name!r})")

    def open(self, name: str) -> _ChunkedReader:
        return _ChunkedReader(self.members[name])


def test_zip_tree_hash_streams_sorted_members_without_archive_read():
    members = {
        "payload/z.txt": "终".encode("utf-8"),
        "payload/a.txt": b"a" * 11,
    }
    archive = _StreamingArchive(members)
    digest = hashlib.sha256()
    for relative in ("a.txt", "z.txt"):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(members["payload/" + relative])
        digest.update(b"\0")

    assert _zip_tree_hash(archive, "payload/") == digest.hexdigest()

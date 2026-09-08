from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from tools.build_plugin import build
from tools.validate_artifact import _zip_tree_hash, validate as validate_artifact


@pytest.fixture(scope="module")
def artifact(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("artifact") / "plugin.zip")


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
            info.compress_type = zipfile.ZIP_DEFLATED
            target_archive.writestr(info, value)


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
    catalog["scope.selected_count"] = "已選取 {selected} 個 XHTML 檔案"
    target = tmp_path / "i18n-placeholder-mismatch.zip"
    _rewrite_archive(artifact, target, {name: json.dumps(catalog, ensure_ascii=False).encode("utf-8")})

    with pytest.raises(SystemExit, match="i18n resource placeholders differ.*scope.selected_count"):
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

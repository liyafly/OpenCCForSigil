"""Versioned profile persistence, validation, and migration.

Profiles contain conversion preferences and references to rule sets.  Rule
documents remain separate, so editing a shared ruleset updates every profile
that references it only after a new plan snapshot is created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping
import uuid

CURRENT_PROFILE_SCHEMA = 1
_SUPPORTED_CONVERSIONS = {
    "s2t",
    "t2s",
    "s2tw",
    "tw2s",
    "s2twp",
    "tw2sp",
    "s2hk",
    "hk2s",
    "s2hkp",
    "hk2sp",
    "t2tw",
    "tw2t",
    "t2hk",
    "hk2t",
    "t2jp",
    "jp2t",
    "s2t_jieba",
    "s2tw_jieba",
    "s2twp_jieba",
    "s2hk_jieba",
    "s2hkp_jieba",
    "tw2sp_jieba",
    "hk2sp_jieba",
}
_KNOWN_FIELDS = {
    "schema_version",
    "id",
    "name",
    "conversion",
    "segmentation",
    "scope",
    "convert_nav",
    "convert_ncx",
    "convert_metadata",
    "convert_alt",
    "convert_title",
    "convert_aria_label",
    "convert_svg_text",
    "convert_ruby_rt",
    "convert_code_pre",
    "decode_numeric_cjk_refs",
    "quotation_mode",
    "punctuation_mode",
    "language_metadata",
    "language_preset",
    "language_region",
    "ruleset_ids",
    "preview_required",
    "pivot_chain",
    "include_nav",
    "include_ncx",
    "include_metadata",
    "attributes",
    "protected_elements",
    "svg_text",
    "mathml",
    "quotation",
    "punctuation",
    "numeric_cjk_char_refs",
    "tofu_policy",
    "regex_rules",
    "force_pivot",
    "review_annotations",
    "checkpoint_notice",
}
_VALID_SCOPES = {"single", "all_xhtml", "spine", "selected"}
_VALID_QUOTATION_MODES = {"keep", "curly", "corner", "nested_corner"}
_VALID_PUNCTUATION_MODES = {"keep", "horizontal"}
_VALID_LANGUAGE_METADATA = {"keep", "suggest", "force"}
_VALID_LANGUAGE_PRESETS = {"legacy", "bcp47"}
_VALID_LANGUAGE_REGIONS = {"", "auto", "zhTW", "zhHK", "zh-TW", "zh-HK"}


class ProfileValidationError(ValueError):
    """Actionable profile validation failure."""


@dataclass(frozen=True)
class Profile:
    schema_version: int = CURRENT_PROFILE_SCHEMA
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    conversion: str = "s2t"
    segmentation: str = "mmseg"
    scope: str = "all_xhtml"
    convert_nav: bool = True
    convert_ncx: bool = False
    convert_metadata: bool = False
    convert_alt: bool = True
    convert_title: bool = True
    convert_aria_label: bool = False
    convert_svg_text: bool = False
    convert_ruby_rt: bool = False
    convert_code_pre: bool = False
    decode_numeric_cjk_refs: bool = False
    quotation_mode: str = "keep"
    punctuation_mode: str = "keep"
    language_metadata: str = "keep"
    language_preset: str = "legacy"
    language_region: str = "auto"
    ruleset_ids: tuple[str, ...] = ()
    preview_required: bool = True
    attributes: tuple[str, ...] = ("alt", "title")
    protected_elements: tuple[str, ...] = ("script", "style", "code", "pre")
    mathml: bool = False
    numeric_cjk_char_refs: str = "keep"
    tofu_policy: str = "native_default_include"
    regex_rules: bool = False
    force_pivot: bool = False
    pivot_chain: tuple[str, ...] = ()
    review_annotations: bool = False
    checkpoint_notice: bool = True
    extras: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, migrate: bool = True) -> "Profile":
        values = migrate_profile_payload(payload) if migrate else dict(payload)
        _validate_payload(values)
        aliases = {
            "include_nav": "convert_nav",
            "include_ncx": "convert_ncx",
            "include_metadata": "convert_metadata",
            "svg_text": "convert_svg_text",
            "quotation": "quotation_mode",
            "punctuation": "punctuation_mode",
        }
        normalized = {aliases.get(key, key): value for key, value in values.items()}
        for key in ("pivot_chain",):
            if key in normalized:
                if not isinstance(normalized[key], (list, tuple)) or not all(
                    isinstance(item, str) for item in normalized[key]
                ):
                    raise ProfileValidationError(f"{key} must be an array of strings")
                normalized[key] = tuple(normalized[key])
        if normalized.get("force_pivot"):
            from core.transformation import FORCE_PIVOT_CHAINS
            if normalized.get("pivot_chain", ()) not in FORCE_PIVOT_CHAINS:
                raise ProfileValidationError("force_pivot requires a supported explicit pivot_chain")
        if "attributes" in normalized:
            if not isinstance(normalized["attributes"], (list, tuple)) or not all(
                isinstance(item, str) for item in normalized["attributes"]
            ):
                raise ProfileValidationError("attributes must be an array of strings")
            attrs = tuple(normalized["attributes"])
            if not set(attrs) <= {"alt", "title", "aria-label"}:
                raise ProfileValidationError("only alt, title and aria-label are writable attributes")
            normalized.setdefault("convert_alt", "alt" in attrs)
            normalized.setdefault("convert_title", "title" in attrs)
            normalized.setdefault("convert_aria_label", "aria-label" in attrs)
            normalized["attributes"] = attrs
        else:
            normalized["attributes"] = tuple(
                name
                for name, enabled in (
                    ("alt", normalized.get("convert_alt", True)),
                    ("title", normalized.get("convert_title", True)),
                    ("aria-label", normalized.get("convert_aria_label", False)),
                )
                if enabled
            )
        if "protected_elements" in normalized:
            if not isinstance(normalized["protected_elements"], (list, tuple)) or not all(
                isinstance(item, str) for item in normalized["protected_elements"]
            ):
                raise ProfileValidationError("protected_elements must be an array of strings")
            normalized["protected_elements"] = tuple(normalized["protected_elements"])
        if "ruleset_ids" in normalized:
            if not isinstance(normalized["ruleset_ids"], (list, tuple)):
                raise ProfileValidationError("ruleset_ids must be an array of rule set IDs")
            if not all(isinstance(item, str) and item for item in normalized["ruleset_ids"]):
                raise ProfileValidationError("ruleset_ids must contain non-empty strings")
            normalized["ruleset_ids"] = tuple(normalized["ruleset_ids"])
        known = {
            "schema_version",
            "include_nav",
            "include_ncx",
            "include_metadata",
            "svg_text",
            "quotation",
            "punctuation",
            "id",
            "name",
            "conversion",
            "segmentation",
            "scope",
            "convert_nav",
            "convert_ncx",
            "convert_metadata",
            "convert_alt",
            "convert_title",
            "convert_aria_label",
            "convert_svg_text",
            "convert_ruby_rt",
            "convert_code_pre",
            "decode_numeric_cjk_refs",
            "quotation_mode",
            "punctuation_mode",
            "language_metadata",
            "language_preset",
            "language_region",
            "ruleset_ids",
            "preview_required",
            "attributes",
            "protected_elements",
            "mathml",
            "numeric_cjk_char_refs",
            "tofu_policy",
            "regex_rules",
            "force_pivot",
            "pivot_chain",
            "review_annotations",
            "checkpoint_notice",
        }
        extras = tuple(
            sorted(
                (key, value)
                for key, value in values.items()
                if key not in known and key != "schema_version"
            )
        )
        accepted = {key: value for key, value in normalized.items() if key in known}
        accepted["extras"] = extras
        return cls(**accepted)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "conversion": self.conversion,
            "segmentation": self.segmentation,
            "scope": self.scope,
            "convert_nav": self.convert_nav,
            "convert_ncx": self.convert_ncx,
            "convert_metadata": self.convert_metadata,
            "convert_alt": self.convert_alt,
            "convert_title": self.convert_title,
            "convert_aria_label": self.convert_aria_label,
            "convert_svg_text": self.convert_svg_text,
            "convert_ruby_rt": self.convert_ruby_rt,
            "convert_code_pre": self.convert_code_pre,
            "decode_numeric_cjk_refs": self.decode_numeric_cjk_refs,
            "quotation_mode": self.quotation_mode,
            "punctuation_mode": self.punctuation_mode,
            "language_metadata": self.language_metadata,
            "language_preset": self.language_preset,
            "language_region": self.language_region,
            "ruleset_ids": list(self.ruleset_ids),
            "preview_required": self.preview_required,
            "attributes": list(self.attributes),
            "protected_elements": list(self.protected_elements),
            "mathml": self.mathml,
            "numeric_cjk_char_refs": self.numeric_cjk_char_refs,
            "tofu_policy": self.tofu_policy,
            "regex_rules": self.regex_rules,
            "force_pivot": self.force_pivot,
            "pivot_chain": list(self.pivot_chain),
            "review_annotations": self.review_annotations,
            "checkpoint_notice": self.checkpoint_notice,
        }
        payload.update(dict(self.extras))
        return payload

    # Read-only compatibility views for existing controller code and profile
    # fixtures while callers migrate to the canonical V1 names.
    @property
    def include_nav(self) -> bool:
        return self.convert_nav

    @property
    def include_ncx(self) -> bool:
        return self.convert_ncx

    @property
    def include_metadata(self) -> bool:
        return self.convert_metadata

    @property
    def quotation(self) -> str:
        return self.quotation_mode

    @property
    def punctuation(self) -> str:
        return self.punctuation_mode


def _validate_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ProfileValidationError("profile must be a JSON object")
    if payload.get("schema_version") != CURRENT_PROFILE_SCHEMA:
        raise ProfileValidationError(
            f"unsupported profile schema_version {payload.get('schema_version')!r}; export or migrate it before loading"
        )
    for key in ("id", "conversion", "segmentation"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ProfileValidationError(f"{key} must be a non-empty string")
    if payload["conversion"] not in _SUPPORTED_CONVERSIONS:
        raise ProfileValidationError(
            f"conversion is not an official V1 config: {payload['conversion']}"
        )
    if payload["segmentation"] not in {"mmseg", "jieba"}:
        raise ProfileValidationError("segmentation must be 'mmseg' or 'jieba'")
    for key, allowed in (
        ("scope", _VALID_SCOPES),
        ("quotation_mode", _VALID_QUOTATION_MODES),
        ("punctuation_mode", _VALID_PUNCTUATION_MODES),
        ("language_metadata", _VALID_LANGUAGE_METADATA),
        ("language_preset", _VALID_LANGUAGE_PRESETS),
        ("language_region", _VALID_LANGUAGE_REGIONS),
    ):
        if key in payload and (not isinstance(payload[key], str) or payload[key] not in allowed):
            raise ProfileValidationError(f"{key} must be one of {sorted(allowed)}")
    for key in ("regex_rules", "svg_text", "convert_svg_text", "review_annotations"):
        if payload.get(key) is True:
            raise ProfileValidationError(f"{key} is a V1.1 feature and cannot be enabled in V1")
    for key in (
        "convert_nav",
        "convert_ncx",
        "convert_metadata",
        "convert_alt",
        "convert_title",
        "convert_aria_label",
        "convert_svg_text",
        "convert_ruby_rt",
        "convert_code_pre",
        "decode_numeric_cjk_refs",
        "preview_required",
        "mathml",
        "regex_rules",
        "force_pivot",
        "review_annotations",
        "checkpoint_notice",
    ):
        if key in payload and not isinstance(payload[key], bool):
            raise ProfileValidationError(f"{key} must be boolean")


def migrate_profile_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ProfileValidationError("profile must be a JSON object")
    result = dict(payload)
    version = result.get("schema_version", 0)
    if version == CURRENT_PROFILE_SCHEMA:
        return result
    if version == 0:
        result["schema_version"] = CURRENT_PROFILE_SCHEMA
        result.setdefault("id", result.get("name") or str(uuid.uuid4()))
        result.setdefault("name", result["id"])
        result.setdefault("conversion", "s2t")
        result.setdefault("segmentation", "mmseg")
        result.setdefault("ruleset_ids", [])
        result.setdefault("preview_required", True)
        return result
    raise ProfileValidationError(
        f"unsupported profile schema_version {version!r}; supported version is 1"
    )


class ProfileStore:
    """Store profiles as individually versioned JSON files with atomic writes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.directory = self.root if self.root.name == "profiles" else self.root / "profiles"

    def save(self, profile: Profile | Mapping[str, Any]) -> Path:
        value = profile if isinstance(profile, Profile) else Profile.from_dict(profile)
        value = Profile.from_dict(value.to_dict())
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(value.id)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{value.id}.", suffix=".tmp", dir=self.directory
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            temporary.write_text(
                json.dumps(value.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ProfileValidationError(f"could not save profile {value.id}: {exc}") from exc
        return path

    def load(self, profile_id: str) -> Profile:
        path = self._path(profile_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProfileValidationError(f"profile not found: {profile_id}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileValidationError(f"could not read profile {profile_id}: {exc}") from exc
        return Profile.from_dict(payload, migrate=True)

    def load_all(self) -> tuple[tuple[Profile, ...], tuple[tuple[str, str], ...]]:
        if not self.directory.exists():
            return (), ()
        profiles = []
        errors = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                profiles.append(
                    Profile.from_dict(json.loads(path.read_text(encoding="utf-8")), migrate=True)
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ProfileValidationError) as exc:
                errors.append((path.name, str(exc)))
        return tuple(profiles), tuple(errors)

    def _path(self, profile_id: str) -> Path:
        if not _safe_file_id(profile_id):
            raise ProfileValidationError("profile id must be a simple filename-safe identifier")
        return self.directory / f"{profile_id}.json"


def load_profile(path_or_id: str | Path, *, root: str | Path | None = None) -> Profile:
    path = Path(path_or_id)
    if path.exists():
        try:
            return Profile.from_dict(json.loads(path.read_text(encoding="utf-8")), migrate=True)
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileValidationError(f"could not read profile {path}: {exc}") from exc
    if root is None:
        raise ProfileValidationError(f"profile not found: {path_or_id}")
    return ProfileStore(root).load(str(path_or_id))


def save_profile(profile: Profile | Mapping[str, Any], root: str | Path) -> Path:
    return ProfileStore(root).save(profile)


def _safe_file_id(value: str) -> bool:
    return (
        bool(value)
        and value not in {".", ".."}
        and all(char not in value for char in ("/", "\\", ":", "\x00"))
    )


__all__ = [
    "CURRENT_PROFILE_SCHEMA",
    "Profile",
    "ProfileStore",
    "ProfileValidationError",
    "load_profile",
    "migrate_profile_payload",
    "save_profile",
]

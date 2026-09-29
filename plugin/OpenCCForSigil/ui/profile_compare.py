"""Pure profile normalization and comparison helpers for the profile chooser."""

from __future__ import annotations

from dataclasses import fields
from typing import Mapping

from app.profiles import Profile


_NON_RUNTIME_FIELDS = {"schema_version", "id", "name", "extras"}
_OBSOLETE_PANEL_OPTIONS = {"diagnose_mixed", "detailed_classification"}


def normalized_profile_values(profile: Profile | Mapping[str, object]) -> dict[str, object]:
    defaults = Profile().to_dict()
    values = dict(defaults)
    values.update(profile.to_dict() if isinstance(profile, Profile) else dict(profile))
    for key in _OBSOLETE_PANEL_OPTIONS:
        values.pop(key, None)
    for key, default in defaults.items():
        if values.get(key) is None:
            values[key] = default
    if values.get("scope") == "all":
        values["scope"] = "all_xhtml"
    if values.get("language_region") == "auto":
        values["language_region"] = ""
    return {key: _normalize(value) for key, value in values.items()}


def compare_profile_settings(
    current: Profile | Mapping[str, object],
    candidate: Profile | Mapping[str, object],
) -> tuple[tuple[str, object, object], ...]:
    """Return runtime-affecting changes as (field, current, candidate)."""

    before = normalized_profile_values(current)
    after = normalized_profile_values(candidate)
    names = tuple(field.name for field in fields(Profile)
                  if field.name not in _NON_RUNTIME_FIELDS)
    return tuple((name, before.get(name), after.get(name)) for name in names
                 if before.get(name) != after.get(name))


def profile_runtime_fields() -> tuple[str, ...]:
    return tuple(field.name for field in fields(Profile)
                 if field.name not in _NON_RUNTIME_FIELDS)


def _normalize(value):
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _normalize(item)) for key, item in value.items()))
    if isinstance(value, (tuple, list)):
        return tuple(_normalize(item) for item in value)
    return value


__all__ = ["compare_profile_settings", "normalized_profile_values",
           "profile_runtime_fields"]

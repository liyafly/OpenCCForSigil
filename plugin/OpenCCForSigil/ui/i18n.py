"""Small, deterministic translation catalog for the plugin UI."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Mapping


SUPPORTED_LANGUAGES = ("zh-Hans", "en", "zh-Hant")
LANGUAGE_LABELS = {"zh-Hans": "简体中文", "en": "English", "zh-Hant": "繁體中文"}
_RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources" / "i18n"


def normalize_language(value: object) -> str:
    """Map Sigil/system locale values to one of the shipped catalogs."""

    if not isinstance(value, str):
        return "en"
    locale = value.strip().replace("_", "-").lower()
    if locale in {"zh-hans", "zh-cn", "zh-sg", "zh-my"} or locale.startswith("zh-hans-"):
        return "zh-Hans"
    if locale in {"zh-hant", "zh-tw", "zh-hk", "zh-mo"} or locale.startswith("zh-hant-"):
        return "zh-Hant"
    if locale == "zh" or locale.startswith("zh-cn-"):
        return "zh-Hans"
    if locale == "en" or locale.startswith("en-"):
        return "en"
    return "en"


def choose_language(explicit: object = None, host: object = None, system: object = None) -> str:
    """Prefer an explicit preference, then Sigil, then the system locale."""

    for candidate in (explicit, host, system):
        if isinstance(candidate, str) and candidate.strip():
            return normalize_language(candidate)
    return "en"


class Translator:
    def __init__(self, language: str = "en", catalogs: Mapping[str, Mapping[str, str]] | None = None):
        self.language = normalize_language(language)
        self._catalogs = dict(catalogs) if catalogs is not None else load_catalogs()
        self._catalogs.setdefault("en", {})

    def set_language(self, language: str) -> None:
        self.language = normalize_language(language)

    def text(self, key: str, **values: object) -> str:
        value = self._catalogs.get(self.language, {}).get(key)
        if value is None:
            value = self._catalogs["en"].get(key, key)
        try:
            return value.format(**values)
        except (KeyError, ValueError):
            return value


def load_catalogs() -> dict[str, dict[str, str]]:
    catalogs: dict[str, dict[str, str]] = {}
    for language in SUPPORTED_LANGUAGES:
        path = _RESOURCE_DIR / f"{language}.json"
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
        ):
            raise ValueError(f"invalid i18n catalog: {path}")
        catalogs[language] = payload
    _validate_catalogs(catalogs)
    return catalogs


def _validate_catalogs(catalogs: Mapping[str, Mapping[str, str]]) -> None:
    expected = set(catalogs["en"])
    for language, catalog in catalogs.items():
        if set(catalog) != expected:
            raise ValueError(f"i18n keys differ for {language}")
        for key in expected:
            placeholders = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", catalogs["en"][key]))
            actual = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", catalog[key]))
            if actual != placeholders:
                raise ValueError(f"i18n placeholders differ for {language}:{key}")


__all__ = [
    "LANGUAGE_LABELS",
    "SUPPORTED_LANGUAGES",
    "Translator",
    "choose_language",
    "load_catalogs",
    "normalize_language",
]

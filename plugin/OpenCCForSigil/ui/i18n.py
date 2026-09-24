"""Small, deterministic translation catalog for the plugin UI."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from ui.qt import exec_dialog


SUPPORTED_LANGUAGES = ("zh-Hans", "en", "zh-Hant")
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


def plugin_window_title(translator: Translator, title: str) -> str:
    """Prefix a translated window name with the plugin's name."""

    app_name = translator.text("app.title")
    prefix = f"{app_name} — "
    value = str(title)
    if value == app_name or value.startswith(prefix):
        return value
    return prefix + value


class CatalogView:
    """Expose one namespaced catalog through the legacy mapping-shaped UI API."""

    def __init__(self, translator: Translator, namespace: str):
        self._translator = translator
        self._namespace = namespace

    def __getitem__(self, key: str) -> str:
        return self._translator.text(f"{self._namespace}.{key}")

    def get(self, key: str, default: str | None = None) -> str | None:
        value = self._translator.text(f"{self._namespace}.{key}")
        return default if value == f"{self._namespace}.{key}" else value


def rule_validation_message(translator: Translator, error: BaseException) -> str:
    """Build a localized row/field summary while keeping parser text in Details."""

    index = getattr(error, "index", None)
    field = str(getattr(error, "field", "") or "")
    field_label = translator.text(f"rules.field.{field}") if field else ""
    if field and field_label == f"rules.field.{field}":
        field_label = translator.text("rules.validation.unknown_field")
    if index is not None and field:
        return translator.text("rules.validation.row_field", row=int(index) + 1, field=field_label)
    if index is not None:
        return translator.text("rules.validation.row", row=int(index) + 1)
    if field:
        return translator.text("rules.validation.field", field=field_label)
    return translator.text("rules.validation.generic")


def settings_error_message(translator: Translator, error: BaseException) -> str:
    """Map known settings validation failures to localized user-facing text."""

    detail = str(error)
    if "explicit Legacy region" in detail:
        return translator.text("options.region_required")
    if "force-pivot" in detail and "end" in detail:
        return translator.text("options.force_pivot_mismatch")
    if "configuration is unavailable on this host" in detail:
        return translator.text("profile.config_unavailable")
    return translator.text("options.invalid")


def configuration_label(translator: Translator, config: str) -> str:
    """Render a conversion configuration without exposing its internal ID."""

    from opencc_backend.configs import BASE_CONFIG_BY_JIEBA

    base = BASE_CONFIG_BY_JIEBA.get(str(config), str(config))
    label = translator.text(f"config.{base}")
    for identifier in {str(config), base}:
        label = label.replace(f" ({identifier})", "").replace(f"（{identifier}）", "")
    if str(config) != base:
        label = translator.text(
            "config.jieba_combination", config=label,
            segmentation=translator.text("config.jieba"))
    return label


def profile_display_name(profile: Any, translator: Translator) -> str:
    """Use the current locale for the built-in profile's visible name."""

    if getattr(profile, "id", None) == "conservative":
        return translator.text("profile.default_name")
    return str(getattr(profile, "name", "") or getattr(profile, "id", ""))


def diagnostic_summary(translator: Translator, code: str, count: int = 1) -> str:
    """Localize known planner diagnostics without exposing internal English text."""

    key = {
        "MIXED_SCRIPT": "diagnostic.mixed_script",
        "INLINE_BOUNDARY": "diagnostic.inline_boundary",
        "QUOTE_UNBALANCED": "diagnostic.quote_unbalanced",
        "SOURCE_INVALID_XHTML": "diagnostic.source_invalid_xhtml",
        "UNPLANNED_CHANGE": "diagnostic.unplanned_change",
        "PROTECTED_ATTRIBUTE_CHANGED": "diagnostic.protected_attribute_changed",
    }.get(code, "diagnostic.unknown")
    return translator.text(key, count=count, code=code)


def show_error_details(qt: Any, parent: Any, title: str, summary: str, detail: str) -> None:
    """Show a translated summary and preserve the original exception in Details."""

    message_box = qt.QMessageBox
    try:
        box = message_box(parent)
    except TypeError:
        box = message_box()
    if not all(callable(getattr(box, name, None)) for name in ("setWindowTitle", "setText")):
        message_box.warning(parent, title, summary)
        return
    box.setWindowTitle(plugin_window_title(Translator(), title))
    box.setText(summary)
    set_details = getattr(box, "setDetailedText", None)
    if callable(set_details):
        set_details(detail)
    if callable(getattr(box, "exec", None)) or callable(getattr(box, "exec_", None)):
        exec_dialog(box)
    else:
        message_box.warning(parent, title, summary)


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
    "CatalogView",
    "SUPPORTED_LANGUAGES",
    "Translator",
    "choose_language",
    "configuration_label",
    "profile_display_name",
    "load_catalogs",
    "normalize_language",
    "diagnostic_summary",
    "rule_validation_message",
    "settings_error_message",
    "show_error_details",
]

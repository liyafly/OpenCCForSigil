"""Shared Qt binding and application helpers for Sigil dialogs."""

from __future__ import annotations

import sys
from typing import Any


_application: Any = None
_host_bk: Any = None
_qt_base_translators: list[Any] = []


def set_host_book(bk: Any) -> None:
    """Remember Sigil's book for its PluginApplication bootstrap."""

    global _host_bk
    _host_bk = bk


def load_qt() -> Any:
    """Load the supported Qt binding and expose its common namespaces."""

    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        try:
            from PyQt5 import QtCore, QtGui, QtWidgets
        except ImportError as exc:
            raise RuntimeError("Sigil Qt runtime is unavailable") from exc
    QtWidgets.Qt = QtCore.Qt
    QtWidgets.QtCore = QtCore
    QtWidgets.QtGui = QtGui
    QtWidgets.QShortcut = getattr(QtGui, "QShortcut", None) or getattr(
        QtWidgets, "QShortcut", None)
    QtWidgets.QKeySequence = QtGui.QKeySequence
    QtWidgets.QTimer = QtCore.QTimer
    return QtWidgets


def ensure_application(qt_widgets: Any, language: str | None = None) -> Any:
    """Return the one process-level QApplication used by every plugin dialog."""

    global _application
    application = qt_widgets.QApplication.instance()
    if application is not None and application is _application:
        return application
    plugin_application_created = False
    if application is None:
        if _host_bk is not None:
            try:
                from plugin_utils import PluginApplication

                application = PluginApplication(
                    sys.argv, bk=_host_bk, match_dark_palette=True)
                plugin_application_created = application is not None
            except Exception:  # noqa: BLE001 - older Sigil or no plugin_utils
                application = None
        if application is None:
            application = qt_widgets.QApplication(sys.argv)
    if not plugin_application_created:
        _install_qt_base_translation(
            qt_widgets, application,
            language or getattr(_host_bk, "sigil_ui_lang", None),
        )
    _application = application
    return application


def _qt_base_locale(language: str | None) -> str | None:
    if not language:
        return None
    normalized = str(language).replace("_", "-").lower()
    if normalized == "en" or normalized.startswith("en-"):
        return None
    if normalized in {"zh-hant", "zh-tw", "zh-hk", "zh-mo"}:
        return "zh_TW"
    if normalized == "zh-hans" or normalized.startswith("zh-cn") or normalized.startswith("zh-hans-"):
        return "zh_CN"
    return None


def _qt_translations_path(qt_core: Any) -> str | None:
    library_info = getattr(qt_core, "QLibraryInfo", None)
    if library_info is None:
        return None
    library_path = getattr(library_info, "LibraryPath", None)
    translations_path = getattr(library_path, "TranslationsPath", None)
    if translations_path is None:
        translations_path = getattr(library_info, "TranslationsPath", None)
    if translations_path is None:
        return None
    path_method = getattr(library_info, "path", None)
    if callable(path_method):
        return path_method(translations_path)
    location_method = getattr(library_info, "location", None)
    if callable(location_method):
        return location_method(translations_path)
    return None


def _install_qt_base_translation(qt_widgets: Any, application: Any, language: str | None) -> bool:
    locale = _qt_base_locale(language)
    qt_core = getattr(qt_widgets, "QtCore", None)
    translator_type = getattr(qt_core, "QTranslator", None)
    if locale is None or translator_type is None:
        return False
    translations_path = _qt_translations_path(qt_core)
    if not translations_path:
        return False
    translator = translator_type(application)
    if not translator.load(f"qtbase_{locale}", translations_path):
        return False
    install_translator = getattr(application, "installTranslator", None)
    if not callable(install_translator):
        return False
    install_translator(translator)
    _qt_base_translators.append(translator)
    return True


def exec_dialog(dialog: Any) -> Any:
    """Execute a modal dialog across Qt 5 and Qt 6 bindings."""

    execute = getattr(dialog, "exec", None) or getattr(dialog, "exec_", None)
    if not callable(execute):
        raise TypeError("Qt dialog does not provide exec() or exec_()")
    return execute()


def enum_value(namespace: Any, name: str) -> Any:
    """Resolve an enum member across flat Qt 5 and nested Qt 6 APIs."""

    if namespace is None:
        return None
    value = getattr(namespace, name, None)
    if value is not None:
        return value
    for enum_name in (
        "WindowType", "Key", "ItemDataRole", "Orientation", "SelectionBehavior",
        "SelectionMode", "ResizeMode", "SizeAdjustPolicy", "ColorRole", "ShortcutContext",
        "TextElideMode", "ToolButtonPopupMode",
        "ToolButtonStyle", "ArrowType", "ButtonRole",
    ):
        enum = getattr(namespace, enum_name, None)
        value = getattr(enum, name, None) if enum is not None else None
        if value is not None:
            return value
    return None


def ask_confirmation(qt: Any, parent: Any, title: str, message: str, translator: Any) -> bool:
    """Show a yes/no confirmation with plugin-localized button labels."""

    from ui.i18n import plugin_window_title

    message_box = qt.QMessageBox
    box = message_box(parent)
    box.setWindowTitle(plugin_window_title(translator, title))
    box.setText(message)
    accept_role = enum_value(message_box, "AcceptRole")
    reject_role = enum_value(message_box, "RejectRole")
    yes = box.addButton(translator.text("common.yes"), accept_role)
    no = box.addButton(translator.text("common.no"), reject_role)
    box.setDefaultButton(no)
    exec_dialog(box)
    return box.clickedButton() is yes


__all__ = [
    "ask_confirmation", "ensure_application", "enum_value", "exec_dialog", "load_qt",
    "set_host_book",
]

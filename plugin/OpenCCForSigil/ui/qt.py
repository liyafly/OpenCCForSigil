"""Shared Qt binding and application helpers for Sigil dialogs."""

from __future__ import annotations

import sys
from typing import Any


_application: Any = None
_host_bk: Any = None


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


def ensure_application(qt_widgets: Any) -> Any:
    """Return the one process-level QApplication used by every plugin dialog."""

    global _application
    application = qt_widgets.QApplication.instance()
    if application is None:
        if _host_bk is not None:
            try:
                from plugin_utils import PluginApplication

                application = PluginApplication(
                    sys.argv, bk=_host_bk, match_dark_palette=True)
            except Exception:  # noqa: BLE001 - older Sigil or no plugin_utils
                application = None
        if application is None:
            application = qt_widgets.QApplication(sys.argv)
    _application = application
    return application


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
        "ToolButtonPopupMode",
        "ToolButtonStyle", "ArrowType", "ButtonRole",
    ):
        enum = getattr(namespace, enum_name, None)
        value = getattr(enum, name, None) if enum is not None else None
        if value is not None:
            return value
    return None


def ask_confirmation(qt: Any, parent: Any, title: str, message: str, translator: Any) -> bool:
    """Show a yes/no confirmation with plugin-localized button labels."""

    message_box = qt.QMessageBox
    box = message_box(parent)
    box.setWindowTitle(title)
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

"""Shared Qt binding and application helpers for Sigil dialogs."""

from __future__ import annotations

import sys
from typing import Any


_application: Any = None


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
        application = qt_widgets.QApplication(sys.argv)
    _application = application
    return application


def exec_dialog(dialog: Any) -> Any:
    """Execute a modal dialog across Qt 5 and Qt 6 bindings."""

    execute = getattr(dialog, "exec", None) or getattr(dialog, "exec_", None)
    if not callable(execute):
        raise TypeError("Qt dialog does not provide exec() or exec_()")
    return execute()


__all__ = ["ensure_application", "exec_dialog", "load_qt"]

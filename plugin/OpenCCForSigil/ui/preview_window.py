"""Minimal Preview UI for the first interactive conversion phase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

from core.preview import PreviewError, PreviewSession
from core.workflow import PlannedDocument


class UIUnavailableError(RuntimeError):
    """Raised when Sigil's bundled Qt runtime cannot be imported."""


@dataclass(frozen=True)
class PreviewOutcome:
    accepted: bool
    previews: Tuple[PreviewSession, ...]


def show_preview(planned: Sequence[PlannedDocument]) -> PreviewOutcome:
    """Show a preview and return the sessions containing user decisions."""

    qt_widgets = _load_qt_widgets()
    previews = tuple(PreviewSession(item.plan) for item in planned)
    application = qt_widgets.QApplication.instance()
    owns_application = application is None
    if application is None:
        import sys

        application = qt_widgets.QApplication(sys.argv)
    dialog = _PreviewDialog(qt_widgets, planned, previews)
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    if owns_application:
        application.quit()
    return PreviewOutcome(accepted=dialog.applied, previews=previews)


def _load_qt_widgets() -> Any:
    try:
        from PySide6 import QtWidgets

        return QtWidgets
    except ImportError:
        try:
            from PyQt5 import QtWidgets

            return QtWidgets
        except ImportError as exc:
            raise UIUnavailableError("Sigil bundled Qt runtime is unavailable") from exc


class _PreviewDialog:
    def __init__(self, qt_widgets: Any, planned, previews: Tuple[PreviewSession, ...]) -> None:
        self._qt = qt_widgets
        self._planned = planned
        self._previews = previews
        self._entries: List[Tuple[PreviewSession, str]] = []
        self.applied = False

        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle("OpenCCForSigil Preview")
        self.dialog.resize(900, 620)
        self._build()
        self._refresh()

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)

        self.summary = qt.QLabel()
        layout.addWidget(self.summary)

        self.list_widget = qt.QListWidget()
        self.list_widget.currentRowChanged.connect(self._show_current)
        layout.addWidget(self.list_widget)

        self.detail = qt.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(150)
        layout.addWidget(self.detail)

        buttons = qt.QHBoxLayout()
        self.accept_this_button = qt.QPushButton("Accept this")
        self.reject_this_button = qt.QPushButton("Skip this")
        self.accept_all_button = qt.QPushButton("Accept all")
        self.reject_all_button = qt.QPushButton("Skip all")
        self.apply_button = qt.QPushButton("Apply accepted changes")
        self.cancel_button = qt.QPushButton("Cancel")
        for button in (
            self.accept_this_button,
            self.reject_this_button,
            self.accept_all_button,
            self.reject_all_button,
            self.apply_button,
            self.cancel_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.accept_this_button.clicked.connect(self._accept_this)
        self.reject_this_button.clicked.connect(self._reject_this)
        self.accept_all_button.clicked.connect(self._accept_all)
        self.reject_all_button.clicked.connect(self._reject_all)
        self.apply_button.clicked.connect(self._apply)
        self.cancel_button.clicked.connect(self.dialog.reject)

    def _refresh(self) -> None:
        self._entries = [
            (preview, change.change_id)
            for preview in self._previews
            for change in preview.changes
        ]
        current_row = self.list_widget.currentRow()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for preview, change_id in self._entries:
            change = next(item for item in preview.changes if item.change_id == change_id)
            decision = preview.decision(change_id)
            prefix = "?" if decision is None else "✓" if decision.value.startswith("accept") else "×"
            text = f"{prefix} {change.file_id}: {change.source!r} → {change.target!r}"
            self.list_widget.addItem(text)
        self.list_widget.blockSignals(False)

        if self._entries:
            row = current_row if 0 <= current_row < len(self._entries) else 0
            self.list_widget.setCurrentRow(row)
        else:
            self.detail.setPlainText("No conversion changes were found.")
        self._update_summary()

    def _update_summary(self) -> None:
        totals = {"total": 0, "accepted": 0, "rejected": 0, "undecided": 0}
        for preview in self._previews:
            for key, value in preview.summary().items():
                totals[key] += value
        self.summary.setText(
            "Changes: {total}   Accepted: {accepted}   Skipped: {rejected}   "
            "Undecided: {undecided}".format(**totals)
        )
        has_current = bool(self._entries)
        self.accept_this_button.setEnabled(has_current)
        self.reject_this_button.setEnabled(has_current)
        self.accept_all_button.setEnabled(totals["undecided"] > 0)
        self.reject_all_button.setEnabled(totals["undecided"] > 0)

    def _show_current(self, row: int) -> None:
        if row < 0 or row >= len(self._entries):
            self.detail.clear()
            return
        preview, change_id = self._entries[row]
        change = next(item for item in preview.changes if item.change_id == change_id)
        self.detail.setPlainText(
            f"Rule: {change.rule_source}\n"
            f"Category: {change.category}    Risk: {change.risk}\n"
            f"Before: {change.context_before}{change.source}{change.context_after}\n"
            f"Change: {change.source!r} → {change.target!r}"
        )

    def _current_entry(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def _accept_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].accept_this(entry[1])
        self._refresh()

    def _reject_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].reject_this(entry[1])
        self._refresh()

    def _accept_all(self) -> None:
        for preview in self._previews:
            preview.accept_all()
        self._refresh()

    def _reject_all(self) -> None:
        for preview in self._previews:
            preview.reject_all()
        self._refresh()

    def _apply(self) -> None:
        try:
            for preview in self._previews:
                preview.finalize()
        except PreviewError as exc:
            self._qt.QMessageBox.warning(self.dialog, "Preview incomplete", str(exc))
            return
        self.applied = True
        self.dialog.accept()

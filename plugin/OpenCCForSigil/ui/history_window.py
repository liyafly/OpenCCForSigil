"""Qt history browser backed by the privacy-safe history service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from logging_ext.history import HistoryError, HistoryStore
from logging_ext.retention import RetentionResult, cleanup, retention_policy
from ui.i18n import Translator
from ui.qt import ask_confirmation, ensure_application, exec_dialog, load_qt






def _local_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime(
            "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


def history_rows(
    records: Sequence[Mapping[str, Any]], *, translator: Any = None,
) -> list[tuple[str, str, str, str, str, str, str]]:
    """Return localized table rows with metadata only."""

    tr = translator or Translator()
    ordered = sorted(records, key=lambda item: str(item.get("recorded_at", "")), reverse=True)
    rows = []
    empty = tr.text("history.empty_value")
    for record in ordered:
        summary = record.get("summary", {})
        if not isinstance(summary, Mapping):
            summary = {}
        status = str(summary.get("status", ""))
        status_text = tr.text(f"history.status.{status}")
        if status_text == f"history.status.{status}":
            status_text = status or empty
        rows.append((
            _local_datetime(str(record.get("recorded_at", ""))),
            str(summary.get("book_label") or empty),
            str(summary.get("profile_id", summary.get("profile", "")) or empty),
            str(summary.get("config", "") or empty),
            str(summary.get("files_changed", summary.get("files_scanned", 0))),
            str(summary.get("changes", 0)),
            status_text,
        ))
    return rows


def cleanup_with_confirmation(
    history_root: Path,
    logs_root: Path,
    confirm: Callable[[RetentionResult], bool],
    *,
    now: datetime | None = None,
) -> tuple[bool, RetentionResult]:
    """Show a dry-run result to the caller before performing explicit cleanup."""

    policy = retention_policy()
    preview = cleanup(history_root, logs_root, **policy, now=now, dry_run=True)
    if not confirm(preview):
        return False, preview
    result = cleanup(history_root, logs_root, **policy, now=now)
    return True, result


def show_history(
    history_root: Path,
    *,
    logs_root: Path | None = None,
    parent: Any = None,
    language: str = "en",
    translator: Any = None,
    on_inspect: Callable[[Mapping[str, Any]], None] | None = None,
    on_export: Callable[[Mapping[str, Any], bool, Any], None] | None = None,
    qt_widgets: Any = None,
) -> Any:
    """Show recent sessions and invoke root callbacks for inspect/export."""

    qt_widgets = qt_widgets or load_qt()
    ensure_application(qt_widgets)
    translator = translator or Translator(language)
    logs_root = Path(logs_root) if logs_root is not None else Path(history_root).parent / "logs"
    try:
        records = HistoryStore(Path(history_root)).load()
    except HistoryError as exc:
        box = qt_widgets.QMessageBox(parent)
        box.setWindowTitle(translator.text("history.title"))
        box.setText(translator.text("history.corrupt"))
        set_details = getattr(box, "setDetailedText", None)
        if callable(set_details):
            set_details(str(exc))
        recover_button = box.addButton(
            translator.text("history.backup_rebuild"), box.ButtonRole.AcceptRole)
        box.addButton(translator.text("history.close"), box.ButtonRole.RejectRole)
        exec_dialog(box)
        if box.clickedButton() is not recover_button:
            return None
        backup = backup_and_rebuild_history(Path(history_root))
        qt_widgets.QMessageBox.information(
            parent,
            translator.text("history.title"),
            translator.text("history.rebuilt", file=backup.name),
        )
        records = HistoryStore(Path(history_root)).load()

    dialog = qt_widgets.QDialog(parent)
    dialog.setWindowTitle(translator.text("history.title"))
    dialog.resize(960, 500)
    layout = qt_widgets.QVBoxLayout(dialog)
    table = qt_widgets.QTableWidget(0, 7, dialog)
    table.setHorizontalHeaderLabels([
        translator.text("history.date"), translator.text("history.file"),
        translator.text("history.profile"), translator.text("history.direction"),
        translator.text("history.files"), translator.text("history.changes"),
        translator.text("history.status"),
    ])
    _configure_history_table(table, qt_widgets)
    _render_table(table, records, qt_widgets, translator)
    table.setSortingEnabled(True)
    table.sortItems(0, _descending_order(qt_widgets))
    header = table.horizontalHeader()
    resize_mode = getattr(qt_widgets.QHeaderView, "ResizeMode", qt_widgets.QHeaderView)
    header.setSectionResizeMode(getattr(resize_mode, "Stretch"))
    layout.addWidget(table)
    empty = qt_widgets.QLabel(translator.text("history.none"), dialog)
    empty.setVisible(not records)
    layout.addWidget(empty)

    buttons = qt_widgets.QHBoxLayout()
    cleanup_button = qt_widgets.QPushButton(translator.text("history.cleanup"), dialog)
    inspect_button = qt_widgets.QPushButton(translator.text("history.open"), dialog)
    export_button = qt_widgets.QPushButton(translator.text("history.export"), dialog)
    close_button = qt_widgets.QPushButton(translator.text("history.close"), dialog)
    for button in (cleanup_button, inspect_button, export_button, close_button):
        button.setAutoDefault(False)
    inspect_button.setDefault(True)
    cleanup_button.setEnabled(bool(records))
    buttons.addWidget(cleanup_button)
    buttons.addStretch(1)
    buttons.addWidget(inspect_button)
    buttons.addWidget(export_button)
    buttons.addWidget(close_button)
    layout.addLayout(buttons)

    def selected() -> Mapping[str, Any] | None:
        row = table.currentRow()
        if row < 0:
            qt_widgets.QMessageBox.information(
                dialog, translator.text("history.title"), translator.text("history.select"))
            return None
        item = table.item(row, 0)
        role = getattr(qt_widgets.Qt, "UserRole", 32)
        session_id = item.data(role) if item is not None else None
        return next((record for record in records if record.get("session_id") == session_id), None)

    def inspect() -> None:
        record = selected()
        if record is not None and on_inspect is not None:
            on_inspect(record)

    def export() -> None:
        record = selected()
        if record is not None and on_export is not None:
            on_export(record, False, None)

    def do_cleanup() -> None:
        def confirm(preview: RetentionResult) -> bool:
            return ask_confirmation(
                qt_widgets, dialog, translator.text("history.cleanup"),
                translator.text("history.cleanup_prompt", sessions=len(preview.removed_sessions),
                                logs=len(preview.removed_log_files)), translator,
            )

        completed, result = cleanup_with_confirmation(Path(history_root), logs_root, confirm)
        if not completed:
            return
        qt_widgets.QMessageBox.information(
            dialog, translator.text("history.cleanup"),
            translator.text("history.cleanup_done", sessions=len(result.removed_sessions),
                            logs=len(result.removed_log_files)),
        )
        records[:] = HistoryStore(Path(history_root)).load()
        _render_table(table, records, qt_widgets, translator)
        empty.setVisible(not records)
        cleanup_button.setEnabled(bool(records))

    inspect_button.clicked.connect(inspect)
    export_button.clicked.connect(export)
    cleanup_button.clicked.connect(do_cleanup)
    table.doubleClicked.connect(lambda *_args: inspect())
    close_button.clicked.connect(dialog.close)
    dialog.history_records = records
    dialog.history_table = table
    dialog.cleanup_button = cleanup_button
    dialog.history_buttons = (cleanup_button, inspect_button, export_button, close_button)
    dialog.show()
    return dialog


def _render_table(table, records, qt, translator) -> None:
    rows = history_rows(records, translator=translator)
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            item = qt.QTableWidgetItem(value)
            if column == 0:
                role = getattr(qt.Qt, "UserRole", 32)
                item.setData(role, records[row].get("session_id"))
            table.setItem(row, column, item)
    table.setSortingEnabled(True)


def _configure_history_table(table, qt):
    view = qt.QAbstractItemView
    no_edit = getattr(view, "NoEditTriggers", None)
    if no_edit is None:
        no_edit = getattr(getattr(view, "EditTrigger", None), "NoEditTriggers", 0)
    table.setEditTriggers(no_edit)
    selection = getattr(view, "SelectionBehavior", view)
    select_rows = getattr(selection, "SelectRows", 1)
    table.setSelectionBehavior(select_rows)
    return no_edit, select_rows


def _descending_order(qt):
    order = getattr(qt.Qt, "SortOrder", qt.Qt)
    return getattr(order, "DescendingOrder", 1)


def backup_and_rebuild_history(history_root: Path) -> Path:
    """Quarantine a corrupt history index and create a valid empty history."""

    root = Path(history_root)
    store = HistoryStore(root)
    from sigil.storage import UserDataStore

    backup = UserDataStore(root.parent).quarantine(store.index_path)
    store.replace_sessions(())
    return backup


__all__ = [
    "backup_and_rebuild_history", "cleanup_with_confirmation", "history_rows", "show_history",
]

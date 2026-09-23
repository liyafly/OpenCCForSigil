"""Qt history browser backed by the privacy-safe history service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from logging_ext.history import HistoryError, HistoryStore
from logging_ext.retention import RetentionResult, cleanup, retention_policy


_LOCAL_CATALOGS = {
    "en": {
        "history.title": "Conversion History", "history.date": "Date",
        "history.file": "Book / File", "history.profile": "Profile",
        "history.direction": "Direction", "history.files": "Files",
        "history.changes": "Changes", "history.status": "Status",
        "history.open": "Inspect Report", "history.export": "Export Metadata",
        "history.close": "Close", "history.none": "No completed conversion sessions.",
        "history.corrupt": "History could not be read: {detail}",
        "history.select": "Select a session first.",
        "history.backup_rebuild": "Back up and rebuild empty history",
        "history.rebuilt": "Corrupt history was backed up as {file}; a new empty history was created.",
        "history.cleanup": "Clean up old records…",
        "history.cleanup_prompt": "Remove {sessions} old sessions and {logs} log files?",
        "history.cleanup_done": "Removed {sessions} sessions and {logs} log files.",
        "history.empty_value": "—", "history.status.success": "Completed",
        "history.status.completed": "Completed", "history.status.partial_failure": "Partial failure",
        "history.status.failed": "Failed", "history.status.cancelled": "Cancelled",
    },
    "zh-Hans": {
        "history.title": "转换历史", "history.date": "日期",
        "history.file": "书名 / 文件", "history.profile": "配置",
        "history.direction": "方向", "history.files": "文件数",
        "history.changes": "变化数", "history.status": "状态",
        "history.open": "查看报告", "history.export": "导出元数据",
        "history.close": "关闭", "history.none": "没有已完成的转换会话。",
        "history.corrupt": "无法读取历史：{detail}", "history.select": "请先选择会话。",
        "history.backup_rebuild": "备份并重建空历史",
        "history.rebuilt": "损坏的历史已备份为 {file}，并已创建空历史。",
        "history.cleanup": "清理旧记录…",
        "history.cleanup_prompt": "将删除 {sessions} 个旧会话和 {logs} 个日志文件，是否继续？",
        "history.cleanup_done": "已删除 {sessions} 个会话和 {logs} 个日志文件。",
        "history.empty_value": "—", "history.status.success": "已完成",
        "history.status.completed": "已完成", "history.status.partial_failure": "部分失败",
        "history.status.failed": "失败", "history.status.cancelled": "已取消",
    },
    "zh-Hant": {
        "history.title": "轉換歷史", "history.date": "日期",
        "history.file": "書名 / 檔案", "history.profile": "設定檔",
        "history.direction": "方向", "history.files": "檔案數",
        "history.changes": "變化數", "history.status": "狀態",
        "history.open": "檢視報告", "history.export": "匯出中繼資料",
        "history.close": "關閉", "history.none": "沒有已完成的轉換工作階段。",
        "history.corrupt": "無法讀取歷史：{detail}", "history.select": "請先選取工作階段。",
        "history.backup_rebuild": "備份並重建空白歷史",
        "history.rebuilt": "損毀的歷史已備份為 {file}，並已建立空白歷史。",
        "history.cleanup": "清理舊記錄…",
        "history.cleanup_prompt": "將刪除 {sessions} 個舊工作階段和 {logs} 個日誌檔，是否繼續？",
        "history.cleanup_done": "已刪除 {sessions} 個工作階段和 {logs} 個日誌檔。",
        "history.empty_value": "—", "history.status.success": "已完成",
        "history.status.completed": "已完成", "history.status.partial_failure": "部分失敗",
        "history.status.failed": "失敗", "history.status.cancelled": "已取消",
    },
}


class _LocalTranslator:
    def __init__(self, language: str = "en") -> None:
        self.language = language if language in _LOCAL_CATALOGS else "en"

    def text(self, key: str, **values: object) -> str:
        value = _LOCAL_CATALOGS[self.language].get(key, _LOCAL_CATALOGS["en"].get(key, key))
        return value.format(**values)


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

    tr = translator or _LocalTranslator()
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


def _load_qt_widgets() -> Any:
    try:
        from PySide6 import QtCore, QtWidgets

        QtWidgets.Qt = QtCore.Qt
        return QtWidgets
    except ImportError:
        try:
            from PyQt5 import QtCore, QtWidgets

            QtWidgets.Qt = QtCore.Qt
            return QtWidgets
        except ImportError as exc:
            raise RuntimeError("Sigil Qt runtime is unavailable") from exc


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

    qt_widgets = qt_widgets or _load_qt_widgets()
    translator = translator or _LocalTranslator(language)
    logs_root = Path(logs_root) if logs_root is not None else Path(history_root).parent / "logs"
    try:
        records = HistoryStore(Path(history_root)).load()
    except HistoryError as exc:
        box = qt_widgets.QMessageBox(parent)
        box.setWindowTitle(translator.text("history.title"))
        box.setText(translator.text("history.corrupt", detail=str(exc)))
        recover_button = box.addButton(
            translator.text("history.backup_rebuild"), box.ButtonRole.AcceptRole)
        box.addButton(translator.text("history.close"), box.ButtonRole.RejectRole)
        exec_method = getattr(box, "exec", None) or box.exec_
        exec_method()
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
            answer = qt_widgets.QMessageBox.question(
                dialog, translator.text("history.cleanup"),
                translator.text("history.cleanup_prompt", sessions=len(preview.removed_sessions),
                                logs=len(preview.removed_log_files)),
            )
            return answer == _yes_value(qt_widgets)

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

    inspect_button.clicked.connect(inspect)
    export_button.clicked.connect(export)
    cleanup_button.clicked.connect(do_cleanup)
    table.doubleClicked.connect(lambda *_args: inspect())
    close_button.clicked.connect(dialog.close)
    dialog.history_records = records
    dialog.history_table = table
    dialog.cleanup_button = cleanup_button
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


def _yes_value(qt):
    box = qt.QMessageBox
    return getattr(box, "Yes", getattr(getattr(box, "StandardButton", object), "Yes", 1))


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

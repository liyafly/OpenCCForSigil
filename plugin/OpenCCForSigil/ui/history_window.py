"""Qt history browser backed by the privacy-safe history service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from logging_ext.history import HistoryError, HistoryStore


_LOCAL_CATALOGS = {
    "en": {
        "history.title": "Conversion History",
        "history.date": "Date",
        "history.file": "Book / File",
        "history.profile": "Profile",
        "history.direction": "Direction",
        "history.files": "Files",
        "history.changes": "Changes",
        "history.status": "Status",
        "history.open": "Inspect Report",
        "history.export": "Export Metadata",
        "history.full_diff": "Include full diff (explicit opt-in)",
        "history.close": "Close",
        "history.none": "No completed conversion sessions.",
        "history.corrupt": "History could not be read: {detail}",
        "history.select": "Select a session first.",
        "history.full_diff_unavailable": "Full diff is available only when supplied in memory by the caller.",
    },
    "zh-Hans": {
        "history.title": "转换历史",
        "history.date": "日期",
        "history.file": "书名 / 文件",
        "history.profile": "配置",
        "history.direction": "方向",
        "history.files": "文件数",
        "history.changes": "变化数",
        "history.status": "状态",
        "history.open": "查看报告",
        "history.export": "导出元数据",
        "history.full_diff": "包含完整差异（明确选择）",
        "history.close": "关闭",
        "history.none": "没有已完成的转换会话。",
        "history.corrupt": "无法读取历史：{detail}",
        "history.select": "请先选择会话。",
        "history.full_diff_unavailable": "只有调用方临时提供内存中的差异时才能导出完整差异。",
    },
    "zh-Hant": {
        "history.title": "轉換歷史",
        "history.date": "日期",
        "history.file": "書名 / 檔案",
        "history.profile": "設定檔",
        "history.direction": "方向",
        "history.files": "檔案數",
        "history.changes": "變化數",
        "history.status": "狀態",
        "history.open": "檢視報告",
        "history.export": "匯出中繼資料",
        "history.full_diff": "包含完整差異（明確選擇）",
        "history.close": "關閉",
        "history.none": "沒有已完成的轉換工作階段。",
        "history.corrupt": "無法讀取歷史：{detail}",
        "history.select": "請先選取工作階段。",
        "history.full_diff_unavailable": "只有呼叫方暫時提供記憶體中的差異時才能匯出完整差異。",
    },
}


class _LocalTranslator:
    def __init__(self, language: str = "en") -> None:
        self.language = language if language in _LOCAL_CATALOGS else "en"

    def text(self, key: str, **values: object) -> str:
        value = _LOCAL_CATALOGS[self.language].get(key, _LOCAL_CATALOGS["en"].get(key, key))
        return value.format(**values)


def history_rows(
    records: Sequence[Mapping[str, Any]],
) -> list[tuple[str, str, str, str, str, str, str]]:
    """Return table-ready metadata rows without document text."""

    rows = []
    for record in records:
        summary = record.get("summary", {})
        if not isinstance(summary, Mapping):
            summary = {}
        rows.append(
            (
                str(record.get("recorded_at", "")),
                str(summary.get("book_name", summary.get("book_path", ""))),
                str(summary.get("profile_id", summary.get("profile", ""))),
                str(summary.get("config", "")),
                str(summary.get("files_changed", summary.get("files_scanned", 0))),
                str(summary.get("changes", 0)),
                str(summary.get("status", "")),
            )
        )
    return rows


def _load_qt_widgets() -> Any:
    try:
        from PySide6 import QtWidgets
    except ImportError as exc:
        raise RuntimeError("PySide6 is required to show conversion history") from exc
    return QtWidgets


def show_history(
    history_root: Path,
    *,
    parent: Any = None,
    language: str = "en",
    translator: Any = None,
    on_inspect: Callable[[Mapping[str, Any]], None] | None = None,
    on_export: Callable[[Mapping[str, Any], bool, Any], None] | None = None,
    full_diff_provider: Callable[[Mapping[str, Any]], Any] | None = None,
    qt_widgets: Any = None,
) -> Any:
    """Show recent sessions and invoke root callbacks for inspect/export."""

    qt_widgets = qt_widgets or _load_qt_widgets()
    translator = translator or _LocalTranslator(language)
    try:
        records = HistoryStore(Path(history_root)).load()
    except HistoryError as exc:
        message = translator.text("history.corrupt", detail=str(exc))
        box = getattr(qt_widgets, "QMessageBox", None)
        if box is not None:
            box.critical(parent, translator.text("history.title"), message)
        return None

    dialog = qt_widgets.QDialog(parent)
    dialog.setWindowTitle(translator.text("history.title"))
    layout = qt_widgets.QVBoxLayout(dialog)
    table = qt_widgets.QTableWidget(len(records), 7, dialog)
    table.setHorizontalHeaderLabels(
        [
            translator.text("history.date"),
            translator.text("history.file"),
            translator.text("history.profile"),
            translator.text("history.direction"),
            translator.text("history.files"),
            translator.text("history.changes"),
            translator.text("history.status"),
        ]
    )
    table.setSelectionBehavior(qt_widgets.QAbstractItemView.SelectionBehavior.SelectRows)
    for row, values in enumerate(history_rows(records)):
        for column, value in enumerate(values):
            table.setItem(row, column, qt_widgets.QTableWidgetItem(value))
    layout.addWidget(table)
    if not records:
        empty = qt_widgets.QLabel(translator.text("history.none"), dialog)
        layout.addWidget(empty)

    full_diff = qt_widgets.QCheckBox(translator.text("history.full_diff"), dialog)
    layout.addWidget(full_diff)
    buttons = qt_widgets.QHBoxLayout()
    inspect_button = qt_widgets.QPushButton(translator.text("history.open"), dialog)
    export_button = qt_widgets.QPushButton(translator.text("history.export"), dialog)
    close_button = qt_widgets.QPushButton(translator.text("history.close"), dialog)
    buttons.addWidget(inspect_button)
    buttons.addWidget(export_button)
    buttons.addWidget(close_button)
    layout.addLayout(buttons)

    def selected() -> Mapping[str, Any] | None:
        index = table.currentRow()
        if index < 0 or index >= len(records):
            message = qt_widgets.QMessageBox.information(
                dialog, translator.text("history.title"), translator.text("history.select")
            )
            del message
            return None
        return records[index]

    def inspect() -> None:
        record = selected()
        if record is not None and on_inspect is not None:
            on_inspect(record)

    def export() -> None:
        record = selected()
        if record is None or on_export is None:
            return
        include_full_diff = bool(full_diff.isChecked())
        diff = full_diff_provider(record) if include_full_diff and full_diff_provider else None
        if include_full_diff and diff is None:
            qt_widgets.QMessageBox.warning(
                dialog,
                translator.text("history.title"),
                translator.text("history.full_diff_unavailable"),
            )
            return
        on_export(record, include_full_diff, diff)

    inspect_button.clicked.connect(inspect)
    export_button.clicked.connect(export)
    close_button.clicked.connect(dialog.close)
    dialog.history_records = records
    dialog.history_table = table
    dialog.show()
    return dialog


__all__ = ["history_rows", "show_history"]

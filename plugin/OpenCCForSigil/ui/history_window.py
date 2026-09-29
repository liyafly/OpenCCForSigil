"""Qt history browser backed by the privacy-safe history service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.profiles import ProfileStore, ProfileValidationError
from logging_ext.history import HistoryError, HistoryStore
from logging_ext.retention import RetentionResult, cleanup, retention_policy
from ui.i18n import Translator, configuration_label, plugin_window_title
from ui.history_filters import filter_history_records
from ui.qt import ask_confirmation, ensure_application, exec_dialog, load_qt
from ui.window_state import restore_window_size






def _local_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime(
            "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


def history_rows(
    records: Sequence[Mapping[str, Any]], *, translator: Any = None,
    profile_store: ProfileStore | None = None,
    profile_name_cache: Mapping[str, str] | None = None,
) -> list[tuple[str, str, str, str, str, str, str]]:
    """Return localized table rows with metadata only."""

    tr = translator or Translator()
    ordered = _ordered_history_records(records)
    rows = []
    empty = tr.text("history.empty_value")
    resolved_profiles: dict[str, str] = {}
    for record in ordered:
        summary = record.get("summary", {})
        if not isinstance(summary, Mapping):
            summary = {}
        status = str(summary.get("status", ""))
        status_text = tr.text(f"history.status.{status}")
        if status_text == f"history.status.{status}":
            status_text = status or empty
        profile_id = str(summary.get("profile_id", summary.get("profile", "")) or "")
        if profile_id and profile_id not in resolved_profiles:
            resolved_profiles[profile_id] = (
                profile_name_cache.get(profile_id)
                if profile_name_cache is not None and profile_id in profile_name_cache
                else _profile_name(profile_id, profile_store))
        config = str(summary.get("config", "") or "")
        rows.append((
            _local_datetime(str(record.get("recorded_at", ""))),
            str(summary.get("book_label") or empty),
            resolved_profiles.get(profile_id, empty),
            configuration_label(tr, config) if config else empty,
            str(summary.get("files_changed", summary.get("files_scanned", 0))),
            str(summary.get("changes", 0)),
            status_text,
        ))
    return rows


def _profile_name(profile_id: str, profile_store: ProfileStore | None) -> str:
    if profile_store is not None:
        try:
            profile = profile_store.load(profile_id)
            return profile.name or profile.id[:8]
        except (OSError, ProfileValidationError):
            pass
    return profile_id[:8]


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
    ui_preferences=None,
) -> Any:
    """Show recent sessions and invoke root callbacks for inspect/export."""

    qt_widgets = qt_widgets or load_qt()
    translator = translator or Translator(language)
    ensure_application(qt_widgets, language=translator.language)
    logs_root = Path(logs_root) if logs_root is not None else Path(history_root).parent / "logs"
    try:
        records = HistoryStore(Path(history_root)).load()
    except HistoryError as exc:
        box = qt_widgets.QMessageBox(parent)
        box.setWindowTitle(plugin_window_title(
            translator, translator.text("history.title")))
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
            plugin_window_title(translator, translator.text("history.title")),
            translator.text("history.rebuilt", file=backup.name),
        )
        records = HistoryStore(Path(history_root)).load()

    dialog = qt_widgets.QDialog(parent)
    dialog.setWindowTitle(plugin_window_title(
        translator, translator.text("history.title")))
    restore_window_size(dialog, ui_preferences, "history_dialog_size", (960, 500))
    layout = qt_widgets.QVBoxLayout(dialog)

    filters = qt_widgets.QHBoxLayout()
    search_edit = qt_widgets.QLineEdit(dialog)
    search_edit.setPlaceholderText(translator.text("history.search_placeholder"))
    filters.addWidget(search_edit, 2)
    direction_filter = qt_widgets.QComboBox(dialog)
    direction_filter.addItem(translator.text("history.filter_all_directions"), "")
    configs = sorted({str(record.get("summary", {}).get("config", "") or "")
                      for record in records
                      if isinstance(record.get("summary", {}), Mapping)
                      and record.get("summary", {}).get("config")})
    for value in configs:
        direction_filter.addItem(configuration_label(translator, value), value)
    filters.addWidget(direction_filter)
    layout.addLayout(filters)
    count_label = qt_widgets.QLabel()
    layout.addWidget(count_label)
    profile_note = qt_widgets.QLabel(translator.text("history.profile_name_note"))
    profile_note.setWordWrap(True)
    layout.addWidget(profile_note)

    table = qt_widgets.QTableWidget(0, 7, dialog)
    table.setHorizontalHeaderLabels([
        translator.text("history.date"), translator.text("history.file"),
        translator.text("history.profile"), translator.text("history.direction"),
        translator.text("history.files"), translator.text("history.changes"),
        translator.text("history.status"),
    ])
    _configure_history_table(table, qt_widgets)
    profile_store = ProfileStore(Path(history_root).parent)
    profile_names = _profile_name_cache(records, profile_store)
    visible_records = list(records)
    _render_table(table, visible_records, qt_widgets, translator,
                  profile_store=profile_store, profile_name_cache=profile_names)
    table.setSortingEnabled(True)
    table.sortItems(0, _descending_order(qt_widgets))
    header = table.horizontalHeader()
    resize_mode = getattr(qt_widgets.QHeaderView, "ResizeMode", qt_widgets.QHeaderView)
    header.setSectionResizeMode(getattr(resize_mode, "Stretch"))
    layout.addWidget(table)
    empty = qt_widgets.QLabel(translator.text("history.none"), dialog)
    empty.setVisible(not visible_records)
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

    action_note = qt_widgets.QLabel(dialog)
    action_note.setWordWrap(True)
    layout.addWidget(action_note)

    role = getattr(qt_widgets.Qt, "UserRole", 32)

    def _row_session_id(row: int) -> str | None:
        item = table.item(row, 0) if row >= 0 else None
        identifier = item.data(role) if item is not None else None
        return str(identifier) if identifier else None

    def update_actions(*_args) -> None:
        has_selection = table.currentRow() >= 0 and _row_session_id(table.currentRow()) is not None
        inspect_button.setEnabled(has_selection and callable(on_inspect))
        export_button.setEnabled(has_selection and callable(on_export))
        if not records:
            action_note.setText("")
        elif not has_selection:
            action_note.setText(translator.text("history.select_action_note"))
        else:
            unavailable = []
            if not callable(on_inspect):
                unavailable.append(translator.text("history.open_unavailable"))
            if not callable(on_export):
                unavailable.append(translator.text("history.export_unavailable"))
            action_note.setText(" ".join(unavailable))

    def refresh_filters(*_args, preserve_session: str | None = None) -> None:
        nonlocal visible_records
        if preserve_session is None:
            preserve_session = _row_session_id(table.currentRow())
        visible_records = filter_history_records(
            records,
            query=search_edit.text(),
            direction=str(direction_filter.currentData() or ""),
            profile_names=profile_names,
            translator=translator,
        )
        _render_table(table, visible_records, qt_widgets, translator,
                      profile_store=profile_store, profile_name_cache=profile_names)
        if preserve_session is not None:
            for row in range(table.rowCount()):
                if _row_session_id(row) == preserve_session:
                    table.selectRow(row)
                    break
        count_label.setText(translator.text(
            "history.count", visible=len(visible_records), total=len(records)))
        empty.setText(translator.text("history.none" if not records else "history.no_matches"))
        empty.setVisible(not visible_records)
        cleanup_button.setEnabled(bool(records))
        update_actions()

    def selected() -> Mapping[str, Any] | None:
        row = table.currentRow()
        if row < 0:
            return None
        session_id = _row_session_id(row)
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
            dialog, plugin_window_title(translator, translator.text("history.cleanup")),
            translator.text("history.cleanup_done", sessions=len(result.removed_sessions),
                            logs=len(result.removed_log_files)),
        )
        records[:] = HistoryStore(Path(history_root)).load()
        profile_names.clear()
        profile_names.update(_profile_name_cache(records, profile_store))
        refresh_filters(preserve_session=None)

    inspect_button.clicked.connect(inspect)
    export_button.clicked.connect(export)
    cleanup_button.clicked.connect(do_cleanup)
    table.doubleClicked.connect(lambda *_args: inspect())
    table.itemSelectionChanged.connect(update_actions)
    search_edit.textChanged.connect(refresh_filters)
    direction_filter.currentIndexChanged.connect(refresh_filters)
    close_button.clicked.connect(dialog.close)
    count_label.setText(translator.text(
        "history.count", visible=len(visible_records), total=len(records)))
    update_actions()
    dialog.history_records = records
    dialog.history_table = table
    dialog.cleanup_button = cleanup_button
    dialog.history_buttons = (cleanup_button, inspect_button, export_button, close_button)
    dialog.history_search = search_edit
    dialog.history_direction_filter = direction_filter
    dialog.history_count_label = count_label
    dialog.history_empty_label = empty
    dialog.history_action_note = action_note
    dialog.show()
    return dialog


def _render_table(table, records, qt, translator, *, profile_store=None,
                  profile_name_cache=None) -> None:
    ordered = _ordered_history_records(records)
    rows = history_rows(ordered, translator=translator, profile_store=profile_store,
                        profile_name_cache=profile_name_cache)
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            item = qt.QTableWidgetItem(value)
            if column in {4, 5}:
                role = getattr(qt.Qt, "DisplayRole", 0)
                item.setData(role, int(value))
            if column == 0:
                role = getattr(qt.Qt, "UserRole", 32)
                item.setData(role, ordered[row].get("session_id"))
            table.setItem(row, column, item)
    table.setSortingEnabled(True)


def _ordered_history_records(records):
    return sorted(records, key=lambda item: (
        str(item.get("recorded_at", "")), str(item.get("session_id", ""))), reverse=True)


def _profile_name_cache(records, profile_store) -> dict[str, str]:
    identifiers = set()
    for record in records:
        summary = record.get("summary", {})
        if isinstance(summary, Mapping):
            identifier = str(summary.get("profile_id", summary.get("profile", "")) or "")
            if identifier:
                identifiers.add(identifier)
    return {identifier: _profile_name(identifier, profile_store) for identifier in identifiers}


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

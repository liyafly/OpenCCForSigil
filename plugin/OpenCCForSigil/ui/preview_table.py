"""Preview change-table row formatting and the lazy Qt table model."""

from __future__ import annotations

from html import unescape

from core.preview import (
    PreviewGroupKind,
    preview_group_kind,
)
from ui.qt import UIUnavailableError, enum_value as _enum_value
from ui.i18n import (
    Translator,
)


_PREVIEW_COLUMNS = (
    "status",
    "file",
    "change",
    "source",
    "target",
    "category",
    "risk",
)


def _single_line(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "↵").replace("\t", "⇥")


def _text_context(change, targets_by_id) -> tuple[str, str]:
    target = (targets_by_id or {}).get((change.file_id, change.target_id))
    if target is None:
        return "", ""
    text = target.source_text
    start = max(0, min(change.span.start - target.source_start, len(text)))
    end = max(start, min(change.span.end - target.source_start, len(text)))
    before_start = max(0, start - 20)
    after_end = min(len(text), end + 20)
    before = text[before_start:start]
    after = text[end:after_end]
    if before_start:
        before = "…" + before
    if after_end < len(text):
        after += "…"
    return before, after


def _source_context(change, sources_by_id) -> tuple[str, str]:
    source = (sources_by_id or {}).get(change.file_id, "")
    start = max(0, min(change.span.start, len(source)))
    end = max(start, min(change.span.end, len(source)))
    return source[max(0, start - 32):start], source[end:min(len(source), end + 32)]


def _format_change_row(
    change, href_by_id, translator, *, trim_context: bool, targets_by_id=None,
) -> tuple[str, ...]:
    before, after = _text_context(change, targets_by_id)
    before = _single_line(before)
    after = _single_line(after)
    if trim_context:
        before = f"…{before[-12:]}" if len(before) > 12 else before
        after = f"{after[:12]}…" if len(after) > 12 else after
    source_text = _single_line(unescape(change.source))
    target_text = _single_line(unescape(change.target))
    source = f"{before}【{source_text}】{after}"
    target = f"{before}【{target_text}】{after}"
    category = translator.text(f"preview.category_value.{change.category}")
    risk = translator.text(f"preview.risk_value.{change.risk.lower()}")
    href = str(
        translator.text("preview.file.metadata")
        if change.document_kind == "metadata"
        else href_by_id.get(change.file_id, change.file_id)
    )
    file_name = href.rsplit("/", 1)[-1] if change.document_kind != "metadata" else href
    return (file_name, f"{source_text} → {target_text}", source, target, category, risk)


def format_change_row(change, href_by_id, translator, targets_by_id=None) -> tuple[str, ...]:
    """Return concise, plain, localized display values for one preview table row."""

    return _format_change_row(
        change, href_by_id, translator, trim_context=True, targets_by_id=targets_by_id)


def _group_marker_key(group_id: str) -> str:
    return {
        PreviewGroupKind.LANGUAGE_METADATA: "preview.group_row_marker",
        PreviewGroupKind.RULE_OCCURRENCE: "preview.rule_group_row_marker",
        PreviewGroupKind.LINKED: "preview.linked_group_row_marker",
    }[preview_group_kind(group_id)]


def _group_explanation_key(group_id: str) -> str:
    return {
        PreviewGroupKind.LANGUAGE_METADATA: "preview.group_explanation",
        PreviewGroupKind.RULE_OCCURRENCE: "preview.rule_group_explanation",
        PreviewGroupKind.LINKED: "preview.linked_group_explanation",
    }[preview_group_kind(group_id)]


def _group_feedback_key(group_id_or_kind, accepted: bool) -> str:
    kind = (group_id_or_kind if isinstance(group_id_or_kind, PreviewGroupKind)
            else preview_group_kind(group_id_or_kind))
    if kind is PreviewGroupKind.LANGUAGE_METADATA:
        verb = "accepted" if accepted else "skipped"
        return f"preview.group_{verb}"
    group = "rule_group" if kind is PreviewGroupKind.RULE_OCCURRENCE else "linked_group"
    verb = "accepted" if accepted else "skipped"
    return f"preview.{group}_{verb}"


class _PreviewTableData:
    """Qt-independent row formatting and filtering boundary for preview UI."""

    def __init__(self, entries, href_by_id, translator, group_stats=None, display_cache=None,
                 targets_by_id=None):
        self.entries = tuple(entries)
        self.href_by_id = href_by_id
        self.translator = translator
        self.group_stats = group_stats or {}
        self.display_cache = display_cache if display_cache is not None else {}
        self.targets_by_id = targets_by_id or {}

    def _status(self, preview, change):
        decision = preview.decision(change.change_id)
        if decision is None:
            return self.translator.text("preview.status.pending")
        if decision.value.startswith("accept"):
            return self.translator.text("preview.status.accepted")
        return self.translator.text("preview.status.skipped")

    def _format(self, row: int) -> tuple[str, ...]:
        _preview, change = self.entries[row]
        values = list(format_change_row(
            change, self.href_by_id, self.translator, self.targets_by_id))
        if change.group_id and change.group_id in self.group_stats:
            count, files = self.group_stats[change.group_id]
            marker_key = _group_marker_key(change.group_id)
            values[4] += " — " + self.translator.text(
                marker_key, count=count, files=files)
        return tuple(values)

    def tooltip_values(self, row: int) -> tuple[str, ...]:
        _preview, change = self.entries[row]
        values = _format_change_row(
            change, self.href_by_id, self.translator, trim_context=False,
            targets_by_id=self.targets_by_id)
        if change.group_id and change.group_id in self.group_stats:
            count, files = self.group_stats[change.group_id]
            marker_key = _group_marker_key(change.group_id)
            values = (*values[:4], values[4] + " — " + self.translator.text(
                marker_key, count=count, files=files), values[5])
        href = str(
            self.translator.text("preview.file.metadata")
            if change.document_kind == "metadata"
            else self.href_by_id.get(change.file_id, change.file_id)
        )
        return (self._status(*self.entries[row]), href, *values[1:])

    def row_count(self) -> int:
        return len(self.entries)

    def row_values(self, row: int) -> tuple[str, ...]:
        preview, change = self.entries[row]
        values = self.display_cache.get(change.change_id)
        if values is None:
            values = self._format(row)
            self.display_cache[change.change_id] = values
        return (self._status(preview, change), *values)


def _create_preview_table_model(
    qt_widgets, entries, href_by_id, group_stats=None, translator: Translator | None = None,
    targets_by_id=None,
):
    translator = translator or Translator("en")
    qt_core = getattr(qt_widgets, "QtCore", None)
    if qt_core is None:
        raise UIUnavailableError("Qt table model support is unavailable")
    qabstract_model = qt_core.QAbstractTableModel
    qt = getattr(qt_widgets, "Qt", None)
    gui = getattr(qt_widgets, "QtGui", None)
    headers = tuple(translator.text(f"preview.column.{name}") for name in _PREVIEW_COLUMNS)
    display_cache = {}

    class PreviewTableModel(qabstract_model):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.rows = _PreviewTableData(
                entries, href_by_id, translator, group_stats, display_cache, targets_by_id)

        def rowCount(self, parent=None):
            if parent is not None and parent.isValid():
                return 0
            return self.rows.row_count()

        def columnCount(self, parent=None):
            if parent is not None and parent.isValid():
                return 0
            return len(_PREVIEW_COLUMNS)

        def data(self, index, role=None):
            if not index.isValid():
                return None
            values = self.rows.row_values(index.row())
            display_role = _enum_value(qt, "DisplayRole")
            if role == display_role:
                return values[index.column()]
            if role == _enum_value(qt, "ToolTipRole"):
                tooltips = self.rows.tooltip_values(index.row())
                return tooltips[index.column()]
            if role == _enum_value(qt, "ForegroundRole") and gui is not None:
                palette = None
                parent_method = getattr(self, "parent", None)
                parent = parent_method() if callable(parent_method) else None
                palette_method = getattr(parent, "palette", None)
                if callable(palette_method):
                    palette = palette_method()
                if palette is None:
                    application = getattr(qt_widgets, "QApplication", None)
                    palette_method = getattr(application, "palette", None)
                    if callable(palette_method):
                        palette = palette_method()

                dark_mode = None
                palette_type = getattr(gui, "QPalette", None)
                base_role = _enum_value(palette_type, "Base")
                color_method = getattr(palette, "color", None)
                if base_role is not None and callable(color_method):
                    base_color = color_method(base_role)
                    lightness_method = getattr(base_color, "lightness", None)
                    if callable(lightness_method):
                        dark_mode = lightness_method() < 128
                if dark_mode is None:
                    return None

                colors = (
                    {
                        translator.text("preview.status.accepted"): "#7fd18b",
                        translator.text("preview.status.skipped"): "#b0b0b0",
                        translator.text("preview.status.pending"): "#f0b050",
                    }
                    if dark_mode else
                    {
                        translator.text("preview.status.accepted"): "#1f6f2e",
                        translator.text("preview.status.skipped"): "#5f5f5f",
                        translator.text("preview.status.pending"): "#8a4d00",
                    }
                )
                color = colors.get(values[0]) if index.column() == 0 else None
                return gui.QColor(color) if color else None
            if role == _enum_value(qt, "FontRole") and gui is not None and index.column() == 6:
                entry = self.rows.entries[index.row()]
                if entry[1].risk in {"HIGH", "REVIEW"}:
                    font = gui.QFont()
                    font.setBold(True)
                    return font
            return None

        def headerData(self, section, orientation, role=None):
            if role != _enum_value(qt, "DisplayRole"):
                return None
            horizontal = _enum_value(qt, "Horizontal")
            return headers[section] if orientation == horizontal and 0 <= section < len(headers) else None

        def set_entries(self, next_entries):
            if self.rows.entries is next_entries:
                return
            self.beginResetModel()
            self.rows = _PreviewTableData(
                next_entries, href_by_id, translator, group_stats, display_cache, targets_by_id)
            self.endResetModel()

        def remove_rows(self, ranges):
            entries = self.rows.entries
            for first, last in ranges:
                if first < 0 or last < first or last >= len(entries):
                    continue
                self.beginRemoveRows(qt_core.QModelIndex(), first, last)
                entries = entries[:first] + entries[last + 1:]
                self.rows = _PreviewTableData(
                    entries, href_by_id, translator, group_stats,
                    display_cache, targets_by_id)
                self.endRemoveRows()
            return entries

        def refresh(self, rows=None):
            if not self.rowCount() or not self.columnCount():
                return
            if rows is None:
                rows = (None,)
            else:
                rows = tuple(dict.fromkeys(row for row in rows if 0 <= row < self.rowCount()))
            if rows == (None,):
                self.dataChanged.emit(
                    self.index(0, 0), self.index(self.rowCount() - 1, 0))
            else:
                for row in rows:
                    self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    return PreviewTableModel

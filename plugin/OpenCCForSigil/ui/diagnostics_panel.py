"""Diagnostic records and the collapsible diagnostics panel."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import re
from typing import Any
from collections.abc import Sequence

from core.models import TokenChange
from core.workflow import PlannedDocument
from ui.qt import enum_value as _enum_value
from ui.i18n import (
    Translator,
    diagnostic_summary,
)


_LINE_BREAK = re.compile(r"\r\n?|\n")


@dataclass(frozen=True, slots=True)
class _DiagnosticRecord:
    file_id: str
    href: str
    code: str
    name: str
    description: str
    location: str
    excerpt: str
    related_changes: tuple[tuple[str, str], ...]


def _source_line_starts(source: str) -> tuple[int, ...]:
    """Index original-source lines, treating CRLF as one newline."""

    return (0, *(match.end() for match in _LINE_BREAK.finditer(source)))


def _line_column_for_offset(starts: tuple[int, ...], offset: int) -> tuple[int, int]:
    line_index = max(0, bisect_right(starts, offset) - 1)
    return line_index + 1, offset - starts[line_index] + 1


def _index_change_spans(file_id: str, changes: tuple[Any, ...]):
    """Index eligible change spans while retaining plan order for review rows."""

    indexed = []
    for original_index, change in enumerate(changes):
        if isinstance(change, TokenChange):
            if change.file_id != file_id:
                continue
            change_span = change.span
            change_start = change_span.start
            change_end = change_span.end
        else:
            change_span = getattr(change, "span", None)
            change_start = getattr(change_span, "start", None)
            change_end = getattr(change_span, "end", None)
            if (getattr(change, "file_id", file_id) != file_id
                    or not isinstance(change_start, int)
                    or not isinstance(change_end, int)):
                continue
        if not isinstance(change_start, int) or not isinstance(change_end, int):
            continue
        indexed.append((change_start, change_end, original_index))
    indexed.sort()
    starts = [start for start, _end, _original_index in indexed]
    prefix_max_end = []
    maximum_end = None
    for _start, end, _original_index in indexed:
        if maximum_end is None or end > maximum_end:
            maximum_end = end
        prefix_max_end.append(maximum_end)
    return indexed, starts, prefix_max_end


def _diagnostic_excerpt(
    source: str, start: int | None, end: int | None,
    line: int | None, column: int | None, starts: tuple[int, ...],
) -> str:
    if not source:
        return ""
    if start is None or end is None or not (0 <= start <= end <= len(source)):
        if line is None or column is None or line < 1 or column < 1:
            return ""
        if line - 1 >= len(starts):
            return ""
        start = min(starts[line - 1] + column - 1, len(source))
        end = start
    # Keep the locator compact even when a diagnostic covers a whole block.
    visible_end = min(end, start + 72)
    before = source[max(0, start - 48):start]
    selected = source[start:visible_end]
    after = source[visible_end:min(len(source), visible_end + 48)]
    marker = selected if selected else "|"
    return f"…{before}【{marker}】{after}…"


def _diagnostic_record_count(planned_documents: Sequence[PlannedDocument]) -> int:
    """Count unique diagnostic rows without building their display content."""

    seen = set()
    for planned in planned_documents:
        source_document = getattr(planned, "source", None)
        plan = getattr(planned, "plan", None)
        if plan is None:
            continue
        file_id = str(
            getattr(source_document, "file_id", "")
            or getattr(plan, "file_id", "")
        )
        for diagnostic in getattr(plan, "diagnostics", ()) or ():
            code = str(getattr(diagnostic, "code", "") or "")
            if not code:
                continue
            span = getattr(diagnostic, "span", None)
            raw_start = getattr(span, "start", None)
            raw_end = getattr(span, "end", None)
            start = raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else None
            end = raw_end if isinstance(raw_end, int) and not isinstance(raw_end, bool) else None
            span_key = (start, end) if start is not None and end is not None else None
            identity = ((file_id, code, span_key,
                         str(getattr(diagnostic, "message", "") or ""))
                        if code == "REGEX_ZERO_WIDTH_SKIPPED"
                        else (file_id, code, span_key))
            seen.add(identity)
    return len(seen)


def _diagnostic_records(
    planned_documents: Sequence[PlannedDocument], translator: Translator,
) -> tuple[_DiagnosticRecord, ...]:
    """Build review rows only from the immutable plan and source snapshot."""

    records = []
    seen = set()
    for planned in planned_documents:
        source_document = getattr(planned, "source", None)
        plan = getattr(planned, "plan", None)
        if plan is None:
            continue
        file_id = str(
            getattr(source_document, "file_id", "")
            or getattr(plan, "file_id", "")
        )
        href = str(getattr(source_document, "href", "") or file_id)
        source_value = getattr(source_document, "source", None)
        has_source = isinstance(source_value, str)
        source = source_value if has_source else ""
        line_starts = None

        def get_line_starts(source=source):
            nonlocal line_starts
            if line_starts is None:
                line_starts = _source_line_starts(source)
            return line_starts

        changes = tuple(getattr(plan, "changes", ()) or ())
        change_index = None
        for diagnostic in getattr(plan, "diagnostics", ()) or ():
            code = str(getattr(diagnostic, "code", "") or "")
            if not code:
                continue
            span = getattr(diagnostic, "span", None)
            raw_start = getattr(span, "start", None)
            raw_end = getattr(span, "end", None)
            start = raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else None
            end = raw_end if isinstance(raw_end, int) and not isinstance(raw_end, bool) else None
            span_key = (start, end) if start is not None and end is not None else None
            message = str(getattr(diagnostic, "message", "") or "")
            identity = ((file_id, code, span_key, message)
                        if code == "REGEX_ZERO_WIDTH_SKIPPED"
                        else (file_id, code, span_key))
            if identity in seen:
                continue
            seen.add(identity)

            line = getattr(diagnostic, "line", None)
            column = getattr(diagnostic, "column", None)
            if not (isinstance(line, int) and line > 0
                    and isinstance(column, int) and column > 0):
                line = column = None
                if has_source and start is not None and 0 <= start <= len(source):
                    line, column = _line_column_for_offset(get_line_starts(), start)
            if line is None or column is None:
                location = translator.text("preview.diagnostic_position_unavailable")
            else:
                location = translator.text(
                    "preview.invalid_source_location", line=line, column=column)

            related = []
            if (start is not None and end is not None and 0 <= start <= end <= len(source)):
                if change_index is None:
                    change_index = _index_change_spans(file_id, changes)
                indexed, starts, prefix_max_end = change_index
                lo = bisect_left(prefix_max_end, start)
                hi = bisect_right(starts, end)
                related_hits = []
                for change_start, change_end, original_index in indexed[lo:hi]:
                    change = changes[original_index]
                    if code == "INLINE_BOUNDARY":
                        # The boundary span contains markup, while the affected
                        # text changes sit exactly on either side. The planner
                        # uses these same endpoints when it raises their risk.
                        overlaps = change_end == start or change_start == end
                    else:
                        overlaps = (
                            change_start <= start <= change_end
                            if start == end
                            else change_start < end and start < change_end
                        )
                    if overlaps:
                        identity = (file_id, str(getattr(change, "change_id", "")))
                        related_hits.append((original_index, identity))
                related_seen = set()
                for _original_index, identity in sorted(related_hits):
                    if identity not in related_seen:
                        related_seen.add(identity)
                        related.append(identity)
            diagnostic_name = translator.text(f"diagnostic.name.{code}", code=code)
            if diagnostic_name == f"diagnostic.name.{code}":
                diagnostic_name = translator.text("diagnostic.name.unknown", code=code)
            description = diagnostic_summary(translator, code, 1)
            if code == "REGEX_ZERO_WIDTH_SKIPPED":
                match = re.match(r"rule (\S+): skipped (\d+) ", message)
                if match:
                    description = translator.text(
                        "rules.zero_width_skipped",
                        id=match.group(1), count=int(match.group(2)))
            if (source and (start is None or end is None
                            or not (0 <= start <= end <= len(source)))
                    and line is not None and column is not None):
                excerpt_starts = get_line_starts()
            else:
                excerpt_starts = line_starts or ()
            records.append(_DiagnosticRecord(
                file_id=file_id,
                href=href,
                code=code,
                name=diagnostic_name,
                description=description,
                location=location,
                excerpt=_diagnostic_excerpt(source, start, end, line, column, excerpt_starts),
                related_changes=tuple(related),
            ))
    return tuple(records)


class _DiagnosticPanel:
    """Read-only, filterable diagnostics backed by frozen source snapshots."""

    def __init__(
        self, qt: Any, records: Sequence[_DiagnosticRecord], translator: Translator,
        on_related_change=None,
    ) -> None:
        self._qt = qt
        self._records = tuple(records)
        self._translator = translator
        self._on_related_change = on_related_change
        self.widget = qt.QWidget()
        layout = qt.QVBoxLayout(self.widget)

        self.toggle = qt.QToolButton()
        self.toggle.setText(translator.text(
            "preview.diagnostics_count", count=len(self._records)))
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName(translator.text("a11y.preview.diagnostics"))
        self.toggle.setToolButtonStyle(_enum_value(qt.Qt, "ToolButtonTextBesideIcon"))
        layout.addWidget(self.toggle)

        self.content = qt.QWidget()
        content_layout = qt.QVBoxLayout(self.content)
        filter_row = qt.QHBoxLayout()
        self.file_filter = qt.QComboBox()
        self.code_filter = qt.QComboBox()
        self._populate_filter(
            self.file_filter,
            translator.text("preview.filter_file"),
            tuple((record.href, record.file_id)
                  for record in self._unique_by_value("file_id")),
            translator,
        )
        self._populate_filter(
            self.code_filter,
            translator.text("preview.diagnostic_code_filter"),
            tuple((record.name, record.code)
                  for record in self._unique_by_value("code")),
            translator,
        )
        for combo in (self.file_filter, self.code_filter):
            combo.setSizeAdjustPolicy(
                _enum_value(qt.QComboBox, "AdjustToMinimumContentsLengthWithIcon"))
            combo.setMinimumContentsLength(10)
            filter_row.addWidget(combo)
            combo.currentIndexChanged.connect(self._refresh)
        self.count_label = qt.QLabel()
        filter_row.addWidget(self.count_label)
        content_layout.addLayout(filter_row)

        self.table = qt.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels((
            translator.text("preview.column.file"),
            translator.text("preview.diagnostic_column.code"),
            translator.text("preview.diagnostic_column.position"),
            translator.text("preview.diagnostic_column.description"),
        ))
        self.table.setSelectionBehavior(
            _enum_value(qt.QAbstractItemView, "SelectRows"))
        self.table.setSelectionMode(
            _enum_value(qt.QAbstractItemView, "SingleSelection"))
        self.table.setEditTriggers(_enum_value(qt.QAbstractItemView, "NoEditTriggers"))
        self.table.setAccessibleName(translator.text("a11y.preview.diagnostics"))
        header = self.table.horizontalHeader()
        interactive = _enum_value(qt.QHeaderView, "Interactive")
        stretch = _enum_value(qt.QHeaderView, "Stretch")
        if interactive is not None and stretch is not None:
            for column in (0, 1, 2):
                header.setSectionResizeMode(column, interactive)
            header.setSectionResizeMode(3, stretch)
        self.table.currentCellChanged.connect(self._row_selected)
        self.table.cellClicked.connect(self._row_selected)
        content_layout.addWidget(self.table)

        self.context = qt.QPlainTextEdit()
        self.context.setReadOnly(True)
        self.context.setAccessibleName(translator.text("a11y.preview.diagnostic_context"))
        self.context.setMinimumHeight(64)
        content_layout.addWidget(self.context)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self.set_expanded)
        self.set_expanded(False)
        self._visible_records: tuple[_DiagnosticRecord, ...] = ()
        self._refresh()

    def _unique_by_value(self, attribute: str) -> tuple[_DiagnosticRecord, ...]:
        selected = set()
        result = []
        for record in self._records:
            value = getattr(record, attribute)
            if value in selected:
                continue
            selected.add(value)
            result.append(record)
        return tuple(result)

    @staticmethod
    def _populate_filter(combo, label, values, translator) -> None:
        combo.addItem(
            f"{label}{translator.text('common.label_separator')}"
            f"{translator.text('preview.filter_all')}", None)
        for display, value in values:
            combo.addItem(str(display), str(value))

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        self.content.setVisible(expanded)
        arrow = _enum_value(
            self._qt.Qt, "DownArrow" if expanded else "RightArrow")
        if arrow is not None:
            self.toggle.setArrowType(arrow)
        if self.toggle.isChecked() != expanded:
            blocked = self.toggle.blockSignals(True)
            try:
                self.toggle.setChecked(expanded)
            finally:
                self.toggle.blockSignals(blocked)

    def _refresh(self, *_args) -> None:
        file_id = self.file_filter.currentData()
        code = self.code_filter.currentData()
        records = tuple(
            record for record in self._records
            if (file_id is None or record.file_id == file_id)
            and (code is None or record.code == code)
        )
        self._visible_records = records
        self.count_label.setText(self._translator.text(
            "preview.diagnostics_visible", visible=len(records), total=len(self._records)))
        blocked = self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(records))
            qt_user_role = _enum_value(self._qt.Qt, "UserRole")
            for row, record in enumerate(records):
                values = (record.href, record.name, record.location,
                          record.description)
                for column, value in enumerate(values):
                    item = self._qt.QTableWidgetItem(str(value))
                    if column == 0 and qt_user_role is not None:
                        item.setData(qt_user_role, row)
                    self.table.setItem(row, column, item)
            if records:
                self.table.setCurrentCell(0, 0)
        finally:
            self.table.blockSignals(blocked)
        if records:
            self._row_selected(0, navigate=False)
        else:
            self.context.setPlainText(
                self._translator.text("preview.diagnostics_no_matches"))

    def _row_selected(self, row: int, *_args, navigate=True) -> None:
        if row < 0 or row >= len(self._visible_records):
            return
        record = self._visible_records[row]
        lines = [
            f"{self._translator.text('preview.diagnostic_column.code')}"
            f"{self._translator.text('common.label_separator')}{record.name}",
            f"{self._translator.text('preview.diagnostic_column.position')}"
            f"{self._translator.text('common.label_separator')}{record.location}",
            self._translator.text("preview.diagnostic_context_label"),
            record.excerpt or self._translator.text("preview.diagnostic_context_unavailable"),
        ]
        if record.related_changes:
            lines.append(self._translator.text(
                "preview.diagnostic_related_changes", count=len(record.related_changes)))
        self.context.setPlainText("\n".join(lines))
        if (navigate and record.related_changes
                and callable(self._on_related_change)):
            self._on_related_change(record.related_changes[0])

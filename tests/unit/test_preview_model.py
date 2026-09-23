import time
from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui import preview_window
from ui.preview_window import (
    _PreviewDialog,
    _PreviewTableData,
    _create_preview_table_model,
    format_change_row,
)


def _change(**values):
    defaults = dict(
        source="软件",
        target="軟體",
        span=SourceSpan(0, 2),
        rule_source="OpenCC:s2twp",
        change_id="change-1",
        file_id="chapter",
        category="regional",
        risk="REVIEW",
        text_context_before="他使用",
        text_context_after="处理",
    )
    defaults.update(values)
    return TokenChange(**defaults)


def test_format_change_row_is_plain_text_with_href_and_context():
    translator = Translator("en")
    change = _change(
        source='说\n“软件😀”',
        target='說\n「軟體😀」',
        text_context_before="他使用",
        text_context_after="处理",
    )

    row = format_change_row(change, {"chapter": "Text/chapter.xhtml"}, translator)

    assert row[0] == "Text/chapter.xhtml"
    assert row[1] == "他使用【说↵“软件😀”】处理"
    assert row[2] == "他使用【說↵「軟體😀」】处理"
    assert "<" not in row[1]
    assert '"' not in row[1]
    assert "\\n" not in row[1]
    assert row[3:] == ("Regional vocabulary", "Review")


def test_format_change_row_localizes_opf_metadata_and_keeps_plain_context():
    translator = Translator("zh-Hans")
    change = _change(
        file_id="metadata",
        document_kind="metadata",
        text_context_before="作者",
        text_context_after="标题",
    )

    row = format_change_row(change, {"metadata": "OPF metadata"}, translator)

    assert row[0] == "OPF 元数据"
    assert "<" not in row[1]
    assert row[1] == "作者【软件】标题"
    assert row[3:] == ("地区词汇", "需复核")


class _FakeAbstractTableModel:
    def __init__(self, _parent=None):
        pass

    def beginResetModel(self):
        pass

    def endResetModel(self):
        pass

    def index(self, row, column):
        return row, column


class _FakeQt:
    class QtCore:
        QAbstractTableModel = _FakeAbstractTableModel

    class Qt:
        DisplayRole = 0
        Horizontal = 1


def test_table_model_row_count_tracks_filtered_entries():
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(_change(),)))
    entry = (preview, preview.changes[0])
    model_type = _create_preview_table_model(_FakeQt, (entry,), {"chapter": "a.xhtml"})

    assert model_type().rowCount() == 1
    assert model_type().rowCount(SimpleNamespace(isValid=lambda: True)) == 0
    assert model_type().columnCount() == 6


def test_table_model_construction_scales_to_large_preview_lists():
    translator = Translator("en")
    change = _change()

    class NoDecision:
        @staticmethod
        def decision(_change_id):
            return None

    entry = (NoDecision(), change)
    for count in (10_000, 50_000):
        entries = (entry,) * count
        started = time.perf_counter()
        model_type = _create_preview_table_model(
            _FakeQt, entries, {"chapter": "Text/chapter.xhtml"})
        model = model_type()
        elapsed = time.perf_counter() - started

        assert model.rowCount() == count
        assert elapsed < 0.2

    assert translator.text("preview.column.status") == "Status"


def test_preview_table_data_formats_each_row_once_and_only_refreshes_status(monkeypatch):
    changes = (_change(change_id="first"), _change(change_id="second", file_id="other"))
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=changes))
    calls = []
    original = preview_window.format_change_row

    def count_format(*args):
        calls.append(args[0].change_id)
        return original(*args)

    monkeypatch.setattr(preview_window, "format_change_row", count_format)
    rows = _PreviewTableData(
        tuple((preview, change) for change in changes), {}, Translator("en"))

    assert calls == ["first", "second"]
    for _ in range(20):
        rows.row_values(0)
        rows.row_values(1)
    assert calls == ["first", "second"]

    preview.accept_this("first")
    rows.refresh_statuses()
    assert rows.row_values(0)[0] == "Accepted"
    assert calls == ["first", "second"]


def test_fifty_thousand_preview_build_filter_and_accept_all_stay_bounded():
    grouped = {}
    for index in range(50_000):
        file_id = f"chapter-{index % 100}.xhtml"
        grouped.setdefault(file_id, []).append(_change(
            change_id=f"change-{index}", file_id=file_id,
            category="character" if index % 2 else "phrase",
            span=SourceSpan(index, index + 2),
        ))
    planned = tuple(
        SimpleNamespace(
            source=SimpleNamespace(file_id=file_id, href=f"Text/{file_id}",
                                   document_kind="xhtml"),
            plan=ConversionPlan(source_sha256="", file_id=file_id, changes=tuple(changes)),
        )
        for file_id, changes in grouped.items()
    )
    previews = tuple(PreviewSession(item.plan) for item in planned)
    qt = make_with_table()

    started = time.perf_counter()
    dialog = _PreviewDialog(qt, planned, previews, Translator("en"), None)
    build_seconds = time.perf_counter() - started

    started = time.perf_counter()
    dialog.category_filter.setCurrentIndex(dialog.category_filter.findData("phrase"))
    filter_seconds = time.perf_counter() - started
    assert len(dialog._visible_entries_cache) == 25_000

    started = time.perf_counter()
    dialog._accept_all()
    accept_all_seconds = time.perf_counter() - started

    assert build_seconds < 2.0
    assert filter_seconds < 1.0
    assert accept_all_seconds < 1.0

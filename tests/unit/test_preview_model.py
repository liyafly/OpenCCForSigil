import random
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

    assert row[0] == "chapter.xhtml"
    assert row[1] == "说↵“软件😀” → 說↵「軟體😀」"
    assert row[2] == "他使用【说↵“软件😀”】处理"
    assert row[3] == "他使用【說↵「軟體😀」】处理"
    assert "<" not in row[2]
    assert '"' not in row[2]
    assert "\\n" not in row[2]
    assert row[4:] == ("Regional vocabulary", "Review")


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
    assert "<" not in row[2]
    assert row[2] == "作者【软件】标题"
    assert row[4:] == ("地区词汇", "需复核")


def test_preview_context_keeps_the_changed_text_visible_when_surrounding_context_is_long():
    change = _change(
        source="后", target="後",
        text_context_before="前" * 50,
        text_context_after="后" * 50,
    )

    row = format_change_row(change, {"chapter": "Text/ch001.xhtml"}, Translator("zh-Hans"))

    assert row[0] == "ch001.xhtml"
    assert row[1] == "后 → 後"
    assert row[2] == f"…{'前' * 12}【后】{'后' * 12}…"


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
        ToolTipRole = 3
        Horizontal = 1


def test_table_model_row_count_tracks_filtered_entries():
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(_change(),)))
    entry = (preview, preview.changes[0])
    model_type = _create_preview_table_model(_FakeQt, (entry,), {"chapter": "a.xhtml"})

    assert model_type().rowCount() == 1
    assert model_type().rowCount(SimpleNamespace(isValid=lambda: True)) == 0
    assert model_type().columnCount() == 7


def test_preview_model_exposes_change_file_path_and_full_tooltips():
    change = _change(
        source="后", target="後",
        text_context_before="很长的前文" * 5,
        text_context_after="很长的后文" * 5,
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(change,)))
    model_type = _create_preview_table_model(
        _FakeQt, ((preview, change),), {"chapter": "Text/ch001.xhtml"})
    model = model_type()

    def index(column):
        return SimpleNamespace(
            isValid=lambda: True,
            row=lambda: 0,
            column=lambda: column,
        )

    assert model.data(index(0), _FakeQt.Qt.DisplayRole) == "Pending"
    assert model.data(index(1), _FakeQt.Qt.DisplayRole) == "ch001.xhtml"
    assert model.data(index(2), _FakeQt.Qt.DisplayRole) == "后 → 後"
    assert model.data(index(1), _FakeQt.Qt.ToolTipRole) == "Text/ch001.xhtml"
    assert model.data(index(2), _FakeQt.Qt.ToolTipRole) == "后 → 後"
    assert "很长的前文" * 5 in model.data(index(3), _FakeQt.Qt.ToolTipRole)


def test_table_model_row_count_scales_to_large_preview_lists():
    change = _change()

    class NoDecision:
        @staticmethod
        def decision(_change_id):
            return None

    entry = (NoDecision(), change)
    for count in (10_000, 50_000):
        entries = (entry,) * count
        model_type = _create_preview_table_model(
            _FakeQt, entries, {"chapter": "Text/chapter.xhtml"})
        model = model_type()

        assert model.rowCount() == count


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
        tuple((preview, change) for change in changes), {}, Translator("en"),
        display_cache={},
    )

    assert calls == []
    rows.row_values(0)
    assert calls == ["first"]
    for _ in range(20):
        rows.row_values(0)
        rows.row_values(1)
    assert calls == ["first", "second"]

    preview.accept_this("first")
    assert rows.row_values(0)[0] == "Accepted"
    assert calls == ["first", "second"]


def test_lazy_row_cache_survives_filters_and_single_decisions(monkeypatch):
    changes = tuple(
        _change(
            change_id=f"change-{index}",
            category="character" if index % 2 else "phrase",
        )
        for index in range(5_000)
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=changes))
    calls = []
    original = preview_window.format_change_row

    def count_format(*args):
        calls.append(args[0].change_id)
        return original(*args)

    monkeypatch.setattr(preview_window, "format_change_row", count_format)
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter", href="Text/chapter.xhtml",
                               document_kind="xhtml"),
        plan=preview.plan,
    ),)
    dialog = _PreviewDialog(
        make_with_table(), planned, (preview,), Translator("en"), None)
    model = dialog.table_model
    assert len(calls) <= len(dialog._visible_entries_cache)

    model.data(model.index(0, 1), dialog._qt.Qt.DisplayRole)
    first_id = changes[0].change_id
    assert calls.count(first_id) == 1
    dialog.category_filter.setCurrentIndex(dialog.category_filter.findData("character"))
    dialog.category_filter.setCurrentIndex(dialog.category_filter.findData(None))
    model.data(model.index(0, 1), dialog._qt.Qt.DisplayRole)

    assert calls.count(first_id) == 1


def test_three_hundred_thousand_preview_build_filter_and_accept_all_stay_bounded():
    grouped = {}
    for index in range(300_000):
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
    dialog._accept_this()
    single_decision_seconds = time.perf_counter() - started

    started = time.perf_counter()
    dialog.category_filter.setCurrentIndex(dialog.category_filter.findData("phrase"))
    filter_seconds = time.perf_counter() - started
    assert len(dialog._visible_entries_cache) == 150_000

    started = time.perf_counter()
    dialog._accept_all()
    accept_all_seconds = time.perf_counter() - started

    assert build_seconds < 2.0
    assert single_decision_seconds < 0.05
    assert filter_seconds < 1.0
    assert accept_all_seconds < 1.0


def test_incremental_totals_match_full_recount_after_random_single_decisions():
    rng = random.Random(60224)
    changes = tuple(
        _change(change_id=f"change-{index}", file_id=f"chapter-{index % 4}")
        for index in range(100)
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=changes))
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter-0", href="Text/chapter-0.xhtml",
                               document_kind="xhtml"),
        plan=preview.plan,
    ),)
    dialog = _PreviewDialog(
        make_with_table(), planned, (preview,), Translator("en"), None)

    for _ in range(100):
        index = rng.randrange(len(changes))
        dialog._set_current_row(index)
        dialog._decide_entry((preview, changes[index]), bool(rng.randrange(2)))

    assert dialog._totals == preview.summary()
    expected_files = {}
    accepted_by_file = {}
    for change in changes:
        decision = preview.decision(change.change_id)
        total, pending = expected_files.get(change.file_id, (0, 0))
        expected_files[change.file_id] = (
            total + 1, pending + (decision is None),
        )
        if decision is not None and decision.value.startswith("accept"):
            accepted_by_file[change.file_id] = accepted_by_file.get(change.file_id, 0) + 1
    assert dialog._file_filter_counts == expected_files
    assert dialog._accepted_count_by_file == accepted_by_file

from types import SimpleNamespace

from core.models import ConversionPlan, Diagnostic, SourceSpan, TokenChange
from core.preview import PreviewSession
from core.workflow import ConversionWorkflow
from tests.support.fake_qt import make_with_table
from ui import preview_window
from ui.preview_window import (
    _PreviewDialog,
    _create_preview_table_model,
    _guarded_preview_dialog,
    format_change_row,
)
from ui.i18n import Translator


class _FakeDialog:
    def __init__(self) -> None:
        self.accept_calls = 0
        self.reject_calls = 0

    def accept(self) -> None:
        self.accept_calls += 1

    def reject(self) -> None:
        self.reject_calls += 1


def _preview_dialog(change_count: int = 3, current_row: int = 1):
    changes = tuple(
        TokenChange(
            source=source,
            target=target,
            span=SourceSpan(index, index + 1),
            rule_source="test-rule",
            change_id=f"change-{index}",
            file_id="chapter.xhtml",
            category="character",
            risk="LOW",
            context_before="before ",
            context_after=" after",
        )
        for index, (source, target) in enumerate((("甲", "乙"), ("丙", "丁"), ("戊", "己")))
    )[:change_count]
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=changes))
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter.xhtml", href="Text/chapter.xhtml",
                               document_kind="xhtml"),
        plan=preview.plan,
    ),)
    qt = make_with_table()
    dialog = _PreviewDialog(qt, planned, (preview,), Translator("en"), None)
    dialog.dialog = _FakeDialog()
    if current_row >= 0:
        dialog._set_current_row(current_row)
    return dialog, preview, dialog.table_model


def _table_dialog(entries, previews, *, current_row=0, category="all", file_id=None,
                  language="en"):
    qt = make_with_table()
    dialog = object.__new__(_PreviewDialog)
    dialog._qt = qt
    dialog._translator = Translator(language)
    dialog._previews = tuple(previews)
    dialog._entries = tuple(entries)
    dialog._visible_entries_cache = tuple(entries)
    dialog._planned = ()
    dialog._href_by_id = {}
    dialog._kind_by_id = {}
    dialog._group_stats = {}
    dialog.file_filter = qt.QComboBox()
    dialog.file_filter.addItem("All", None)
    for value in dict.fromkeys(change.file_id for _, change in entries):
        dialog.file_filter.addItem(value, value)
    if file_id is not None:
        dialog.file_filter.setCurrentIndex(dialog.file_filter.findData(file_id))
    dialog.category_filter = qt.QComboBox()
    dialog.category_filter.addItem("All", None)
    for value in sorted({change.category for _, change in entries}):
        dialog.category_filter.addItem(value, value)
    if category != "all":
        dialog.category_filter.setCurrentIndex(dialog.category_filter.findData(category))
    dialog.risk_filter = qt.QComboBox()
    dialog.summary = qt.QLabel()
    dialog.detail = qt.QPlainTextEdit()
    dialog.apply_button = qt.QPushButton()
    dialog.apply_status_label = qt.QLabel()
    dialog.table_view = qt.QTableView()
    dialog.table_model = _create_preview_table_model(
        qt, entries, {}, translator=dialog._translator)(dialog.table_view)
    dialog.table_view.setModel(dialog.table_model)
    dialog._set_current_row(current_row)
    return dialog


def _display(dialog, row, column):
    index = dialog.table_model.index(row, column)
    return dialog.table_model.data(index, dialog._qt.Qt.DisplayRole)


def test_preview_dialog_buttons_are_never_default_or_auto_default():
    dialog, _preview, _model = _preview_dialog()

    buttons = (
        dialog.accept_this_button, dialog.reject_this_button,
        dialog.accept_file_button, dialog.reject_file_button,
        dialog.accept_all_button, dialog.reject_all_button,
        dialog.accept_filter_button, dialog.reject_filter_button,
        dialog.export_button, dialog.apply_button,
        dialog.back_settings_button, dialog.cancel_button,
    )
    assert all(not button.default and button.auto_default is False for button in buttons)


def test_preview_dialog_focuses_change_table_on_open():
    dialog, _preview, _model = _preview_dialog()

    assert any(name == "setFocus" for name, _args in dialog.table_view.calls)


def test_single_decision_refreshes_only_its_status_cell():
    dialog, _preview, model = _preview_dialog(change_count=3, current_row=1)
    ranges = []
    model.dataChanged.connect(
        lambda top, bottom: ranges.append(
            (top.row(), bottom.row(), top.column(), bottom.column())))

    dialog._accept_this()

    assert ranges == [(1, 1, 0, 0)]


def test_preview_table_uses_interactive_columns_and_resizes_once():
    dialog, _preview, _model = _preview_dialog()
    header = dialog.table_view.horizontalHeader()

    assert [args for name, args in header.calls if name == "setSectionResizeMode"] == [
        (0, dialog._qt.QHeaderView.Interactive),
        (1, dialog._qt.QHeaderView.Interactive),
        (4, dialog._qt.QHeaderView.Interactive),
        (5, dialog._qt.QHeaderView.Interactive),
        (2, dialog._qt.QHeaderView.Stretch),
        (3, dialog._qt.QHeaderView.Stretch),
    ]
    assert ("setResizeContentsPrecision", (50,)) in header.calls
    assert dialog.table_view.calls.count(("resizeColumnsToContents", ())) == 1


def test_preview_dialog_single_decisions_update_only_selected_row_and_summary():
    dialog, preview, _model = _preview_dialog()

    dialog._accept_this()
    assert dialog._current_row() == 2
    assert _display(dialog, 1, 0) == "Accepted"
    assert _display(dialog, 0, 0) == "Pending"
    assert "Accepted: 1" in dialog.summary.text()
    assert "Undecided: 2" in dialog.summary.text()
    assert "Remaining: 2" == dialog.apply_status_label.text()
    assert "己" in dialog.detail.toPlainText()
    assert dialog.apply_button.isEnabled() is False

    dialog._reject_this()
    assert dialog._current_row() == 0
    assert _display(dialog, 2, 0) == "Skipped"
    assert "Accepted: 1" in dialog.summary.text()
    assert "Skipped: 1" in dialog.summary.text()
    assert "Undecided: 1" in dialog.summary.text()
    assert "乙" in dialog.detail.toPlainText()
    dialog._accept_this()
    assert dialog.apply_status_label.text() == "Ready to apply."
    assert dialog.apply_button.text() == "Apply 2 changes to 1 file"


def test_preview_dialog_apply_blocks_undecided_and_accepts_decided_without_finalizing():
    dialog, preview, _model = _preview_dialog(change_count=2, current_row=0)
    finalize_calls = []
    preview.finalize = lambda: finalize_calls.append(True)

    dialog._apply()
    assert dialog.applied is False
    assert dialog.dialog.accept_calls == 0
    assert finalize_calls == []
    assert dialog.apply_button.isEnabled() is False
    assert dialog.apply_button.toolTip() == Translator("en").text("preview.incomplete")

    dialog._accept_this()
    dialog._set_current_row(1)
    dialog._reject_this()
    assert dialog.apply_button.isEnabled() is True

    dialog._apply()
    assert dialog.applied is True
    assert dialog.dialog.accept_calls == 1
    assert finalize_calls == []
    assert dialog.apply_button.isEnabled() is False

    dialog._apply()
    assert dialog.dialog.accept_calls == 1


def test_preview_dialog_next_and_previous_select_undecided_entries_only():
    dialog, preview, _model = _preview_dialog(change_count=3, current_row=1)
    preview.accept_this("change-1")

    dialog._previous_undecided()
    assert dialog._current_row() == 0
    dialog._next_undecided()
    assert dialog._current_row() == 2

    preview.accept_all(overwrite=True)
    dialog._set_current_row(1)
    dialog._next_undecided()
    assert dialog._current_row() == 1


def test_refresh_restores_current_change_id_after_filtering():
    first = TokenChange(
        source="甲", target="乙", span=SourceSpan(0, 1), rule_source="rule",
        change_id="first", file_id="a.xhtml", category="character")
    second = TokenChange(
        source="丙", target="丁", span=SourceSpan(1, 2), rule_source="rule",
        change_id="second", file_id="b.xhtml", category="phrase")
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(first, second)))
    entries = tuple((preview, change) for change in preview.changes)
    dialog = _table_dialog(entries, (preview,), current_row=1, category="phrase")

    dialog._refresh()

    assert dialog._visible_entries_cache == ((preview, second),)
    assert dialog._current_row() == 0


def test_file_filter_counts_refresh_without_changing_selection():
    dialog, _preview, _model = _preview_dialog(change_count=3, current_row=0)
    file_filter = dialog.file_filter
    file_filter.setCurrentIndex(file_filter.findData("chapter.xhtml"))
    selected = file_filter.currentData()

    dialog._accept_all()

    assert file_filter.currentData() == selected
    assert file_filter.itemText(file_filter.currentIndex()).endswith("3 changes / 0 undecided")


def test_apply_status_has_pending_ready_and_no_change_states_in_both_chinese_and_english():
    for language in ("en", "zh-Hans"):
        dialog, preview, _model = _preview_dialog(change_count=2, current_row=0)
        dialog._translator = Translator(language)
        dialog._update_summary()
        assert dialog.apply_button.toolTip() == dialog._translator.text("preview.incomplete")
        assert "2" in dialog.apply_status_label.text()

        dialog._accept_all()
        dialog._update_summary()
        assert dialog.apply_status_label.text() == dialog._translator.text(
            "preview.apply_status_ready")
        assert "2" in dialog.apply_button.text()

        dialog._reject_all()
        dialog._update_summary()
        assert dialog.apply_button.text() == dialog._translator.text(
            "preview.apply_no_changes")
        assert dialog.apply_status_label.text() == dialog._translator.text(
            "preview.apply_status_none")


def test_preview_decoding_is_display_only_and_group_feedback_clears_on_normal_action():
    change = TokenChange(
        source="A&amp;", target="A&amp;B", span=SourceSpan(0, 6),
        rule_source="test", change_id="normal", file_id="a.xhtml",
        category="character", risk="LOW",
    )
    group_change = TokenChange(
        source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
        rule_source="language_metadata", change_id="group", file_id="a.xhtml",
        category="language_metadata", risk="HIGH", group_id="language_metadata",
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(group_change, change)))
    dialog = _table_dialog(
        tuple((preview, item) for item in preview.changes), (preview,), current_row=0)
    dialog._group_stats = {"language_metadata": (1, 1)}
    dialog.table_model.rows.group_stats = dialog._group_stats
    dialog._accept_this()
    assert dialog._last_group_feedback
    dialog._set_current_row(1)
    dialog._show_current(1)
    row = dialog.table_model.rows.row_values(1)

    assert row[3] == "【A&B】"
    assert "A&B" in dialog.detail.toPlainText()
    assert "A&amp;B" not in dialog.detail.toPlainText()
    assert change.target == "A&amp;B"

    dialog._reject_this()
    assert dialog._last_group_feedback == ""
    assert "Decided together" not in dialog.summary.text()


def test_filtered_group_decision_reaches_hidden_language_metadata_entries():
    changes = (
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-visible",
            file_id="chapter.xhtml", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-hidden",
            file_id="content.opf", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
        TokenChange(
            source="后", target="後", span=SourceSpan(6, 7),
            rule_source="OpenCC:s2t", change_id="character-visible",
            file_id="chapter.xhtml", category="character", risk="LOW",
        ),
    )
    first = PreviewSession(ConversionPlan(source_sha256="", changes=(changes[0], changes[2])))
    second = PreviewSession(ConversionPlan(source_sha256="", changes=(changes[1],)))
    dialog = _table_dialog(
        tuple((preview, change) for preview in (first, second) for change in preview.changes),
        (first, second), current_row=0, file_id="chapter.xhtml")
    dialog._refresh = lambda **_kwargs: None
    dialog._decide_filtered(True)

    assert first.decision("language-visible").value == "accept_this"
    assert second.decision("language-hidden").value == "accept_this"
    assert first.decision("character-visible").value == "accept_this"


def test_accept_file_leaves_language_group_pending_until_separate_group_action():
    changes = (
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-a",
            file_id="a.xhtml", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
        TokenChange(
            source="甲", target="乙", span=SourceSpan(6, 7),
            rule_source="OpenCC:s2t", change_id="normal-a",
            file_id="a.xhtml", category="character", risk="LOW",
        ),
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-b",
            file_id="b.xhtml", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
        TokenChange(
            source="丙", target="丁", span=SourceSpan(6, 7),
            rule_source="OpenCC:s2t", change_id="normal-b",
            file_id="b.xhtml", category="character", risk="LOW",
        ),
    )
    first = PreviewSession(ConversionPlan(source_sha256="", changes=changes[:2]))
    second = PreviewSession(ConversionPlan(source_sha256="", changes=changes[2:]))
    previews = (first, second)
    entries = tuple((preview, change) for preview in previews for change in preview.changes)
    dialog = _table_dialog(entries, previews, current_row=0, file_id="a.xhtml")
    dialog._visible_entries_cache = entries[:2]
    dialog._group_stats = {"language_metadata": (2, 2)}

    dialog._accept_file()

    assert first.decision("normal-a").value == "accept_this"
    assert first.decision("language-a") is None
    assert second.decision("language-b") is None

    dialog._decide_current_file_groups(True)
    assert first.decision("language-a").value == "accept_this"
    assert second.decision("language-b").value == "accept_this"
    second.accept_this("normal-b")

    workflow = object.__new__(ConversionWorkflow)
    workflow._planned = tuple(SimpleNamespace(plan=preview.plan) for preview in previews)
    finalized = workflow.finalize(previews)
    assert len(finalized) == 2


def test_language_group_row_includes_change_and_file_counts():
    changes = (
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-a",
            file_id="a.xhtml", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-b",
            file_id="b.xhtml", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=changes))
    from ui.preview_window import _PreviewTableData

    row = _PreviewTableData(
        ((preview, changes[0]),),
        {"a.xhtml": "Text/a.xhtml"},
        Translator("en"),
        {"language_metadata": (2, 2)},
    ).row_values(0)

    assert "Language tag group (2 changes / 2 files)" in row[4]


def test_preview_row_truncates_long_text_but_detail_keeps_full_text():
    source = "前" * 300
    change = TokenChange(
        source=source, target="後" * 300, span=SourceSpan(0, 300),
        rule_source="OpenCC:s2t", change_id="long", file_id="chapter.xhtml",
    )
    row = format_change_row(change, {"chapter.xhtml": "Text/chapter.xhtml"}, Translator("en"))

    assert source in row[1]
    assert "後" * 300 in row[2]


def test_plan_diagnostics_are_visible_in_summary_and_detail():
    change = TokenChange(
        source="后", target="後", span=SourceSpan(0, 1), rule_source="OpenCC:s2t",
        change_id="diagnostic", file_id="chapter.xhtml",
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(change,)))
    dialog = _table_dialog(((preview, change),), (preview,))
    dialog._planned = (
        type("Planned", (), {"plan": ConversionPlan(
            source_sha256="", file_id="chapter.xhtml", diagnostics=(
                Diagnostic("MIXED_SCRIPT", "mixed script input"),
                Diagnostic("INLINE_BOUNDARY", "inline boundary"),
            ),
        )})(),
    )

    dialog._update_summary()
    dialog._show_current(0)

    translator = Translator("en")
    assert translator.text("diagnostic.mixed_script", count=1) in dialog.summary.text()
    assert translator.text("diagnostic.inline_boundary", count=1) in dialog.summary.text()
    assert translator.text("diagnostic.mixed_script", count=1) in dialog.detail.toPlainText()
    assert "mixed script input" not in dialog.detail.toPlainText()


def test_summary_lists_skipped_source_href_with_original_line_and_column():
    dialog = object.__new__(_PreviewDialog)
    dialog._translator = Translator("zh-Hans")
    dialog._previews = ()
    dialog._entries = ()
    dialog._planned = (
        SimpleNamespace(
            source=SimpleNamespace(file_id="bad", href="Text/bad.xhtml"),
            plan=ConversionPlan(
                source_sha256="", file_id="bad",
                diagnostics=(Diagnostic(
                    "SOURCE_INVALID_XHTML", "invalid", line=5, column=10),),
            ),
        ),
    )
    dialog.summary = make_with_table().QLabel()
    dialog.apply_button = make_with_table().QPushButton()
    dialog.apply_status_label = make_with_table().QLabel()

    dialog._update_summary()

    assert "Text/bad.xhtml" in dialog.summary.text()
    assert "第 5 行第 10 列" in dialog.summary.text()


def test_preview_exit_confirmation_protects_decisions_and_allows_empty_exit():
    dialog, preview, _items = _preview_dialog(change_count=1, current_row=0)
    confirm_calls = []
    dialog._confirm_discard_decisions = lambda: confirm_calls.append(True) or False
    preview.accept_this("change-0")

    assert dialog._guard_reject() is False
    assert confirm_calls == [True]
    dialog._back_to_settings()
    assert dialog.back_to_settings is False
    assert dialog.dialog.reject_calls == 0

    empty_dialog, _empty_preview, _ = _preview_dialog(change_count=0, current_row=-1)
    empty_dialog._qt = object()
    assert empty_dialog._guard_reject() is True


def test_return_to_scope_confirms_discarded_decisions_once():
    dialog, preview, _items = _preview_dialog(change_count=1, current_row=0)
    preview.reject_this("change-0")
    dialog._confirm_discard_decisions = lambda: True
    dialog.dialog = _guarded_preview_dialog(
        type("Qt", (), {"QDialog": _FakeDialog}), dialog._guard_reject)

    dialog._back_to_settings()

    assert dialog.back_to_settings
    assert dialog.dialog.reject_calls == 1
    assert dialog._allow_reject is False


def test_error_dialog_uses_close_as_default_not_details(monkeypatch):
    qt = make_with_table()
    shown = []
    monkeypatch.setattr(preview_window, "_load_ui_qt", lambda _translator: qt)
    monkeypatch.setattr(preview_window, "ensure_application", lambda *_args: None)
    monkeypatch.setattr(preview_window, "exec_dialog", lambda dialog: shown.append(dialog))

    preview_window.show_error(
        kind="UNEXPECTED",
        detail="RuntimeError",
        files_written=0,
        log_path="/tmp/plugin.log",
    )

    dialog = shown[0]
    details_button = dialog._layout.children[3]
    copy_button, close_button = dialog._layout.children[-1].children
    assert details_button.autoDefault() is False
    assert copy_button.autoDefault() is False
    assert close_button.autoDefault() is False
    assert close_button.isDefault()


def test_preview_export_failure_is_shown_to_the_user(monkeypatch):
    dialog, _preview, _model = _preview_dialog()
    dialog._services = SimpleNamespace(
        export_preview=lambda *_args: (_ for _ in ()).throw(RuntimeError("disk full")))
    warnings = []
    monkeypatch.setattr(
        dialog._qt.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, message: warnings.append((parent, title, message))),
    )

    dialog._export_preview()

    assert len(warnings) == 1
    assert "disk full" in warnings[0][2]

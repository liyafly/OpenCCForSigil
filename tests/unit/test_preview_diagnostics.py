from types import SimpleNamespace

from core.models import ConversionPlan, Diagnostic, SourceSpan, TokenChange
from core.preview import PreviewDecision, PreviewSession
from core.workflow import PlannedDocument, SourceDocument
from tests.support.fake_qt import make_with_table
from ui import preview_window
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog, _diagnostic_records


def _planned(file_id, href, source, diagnostics, changes=()):
    plan = ConversionPlan(
        source_sha256="snapshot",
        file_id=file_id,
        changes=tuple(changes),
        diagnostics=tuple(diagnostics),
    )
    return PlannedDocument(
        SourceDocument(file_id=file_id, href=href, source=source),
        SimpleNamespace(),
        plan,
    )


def test_diagnostic_location_uses_original_python_offsets_and_crlf_lines():
    source = "head\r\nA😀e\u0301汉 end"
    start = source.index("汉")
    planned = _planned(
        "chapter", "Text/chapter.xhtml", source,
        (Diagnostic("INLINE_BOUNDARY", "internal message must stay hidden",
                    SourceSpan(start, start + 1)),),
    )

    (record,) = _diagnostic_records((planned,), Translator("en"))

    assert record.location == "line 2, column 5"
    assert "A😀e\u0301【汉】 end" in record.excerpt
    assert "internal message" not in record.description + record.excerpt


def test_diagnostic_records_deduplicate_by_file_code_and_span():
    source = "甲gap乙"
    diagnostic = Diagnostic("INLINE_BOUNDARY", "private detail", SourceSpan(1, 4))
    changes = (
        TokenChange(
            source="甲", target="乙", span=SourceSpan(0, 1), rule_source="rule",
            change_id="before", file_id="chapter",
        ),
        TokenChange(
            source="gap", target="gap", span=SourceSpan(4, 5), rule_source="rule",
            change_id="after", file_id="chapter",
        ),
    )
    planned = _planned(
        "chapter", "Text/chapter.xhtml", source,
        (diagnostic, diagnostic),
        changes,
    )

    records = _diagnostic_records((planned,), Translator("zh-Hans"))

    assert len(records) == 1
    assert records[0].name == "行内标签边界"
    assert records[0].description == "跨内联标签文本：1 处"
    assert records[0].location == "第 1 行第 2 列"
    assert records[0].related_changes == (
        ("chapter", "before"), ("chapter", "after"))


def test_existing_diagnostic_kinds_have_localized_names_and_summaries():
    planned = _planned(
        "chapter", "Text/chapter.xhtml", "甲乙丙丁",
        (
            Diagnostic("MIXED_SCRIPT", "hidden", SourceSpan(0, 1)),
            Diagnostic("INLINE_BOUNDARY", "hidden", SourceSpan(1, 2)),
            Diagnostic("QUOTE_UNBALANCED", "hidden", SourceSpan(2, 3)),
            Diagnostic("SOURCE_INVALID_XHTML", "hidden", line=4, column=8),
        ),
    )

    records = _diagnostic_records((planned,), Translator("zh-Hans"))

    assert [record.name for record in records] == [
        "简繁混杂", "行内标签边界", "引号未配对", "已跳过格式错误的源文件"]
    assert all(record.description and "hidden" not in record.description
               for record in records)
    assert records[-1].location == "第 4 行第 8 列"


def test_inline_boundary_links_only_to_changes_touching_its_source_edges():
    changes = (
        TokenChange(
            source="甲", target="甲", span=SourceSpan(0, 1), rule_source="rule",
            change_id="before", file_id="chapter",
        ),
        TokenChange(
            source="乙", target="乙", span=SourceSpan(4, 5), rule_source="rule",
            change_id="after", file_id="chapter",
        ),
        TokenChange(
            source="丙", target="丙", span=SourceSpan(6, 7), rule_source="rule",
            change_id="unrelated", file_id="chapter",
        ),
    )
    planned = _planned(
        "chapter", "Text/chapter.xhtml", "甲<em>乙</em>丙",
        (Diagnostic("INLINE_BOUNDARY", "boundary", SourceSpan(1, 4)),),
        changes,
    )

    (record,) = _diagnostic_records((planned,), Translator("en"))

    assert record.related_changes == (("chapter", "before"), ("chapter", "after"))


def test_diagnostic_without_span_or_explicit_position_does_not_guess():
    planned = _planned(
        "chapter", "Text/chapter.xhtml", "原文里有可见文字",
        (Diagnostic("QUOTE_UNBALANCED", "private planner text"),),
    )

    (record,) = _diagnostic_records((planned,), Translator("en"))

    assert record.location == "Position unavailable"
    assert record.excerpt == ""
    assert "private planner text" not in record.description


def test_diagnostic_panel_filters_files_and_codes_and_can_navigate_without_deciding():
    source = "<p>甲<em>乙</em></p>"
    change = TokenChange(
        source="甲", target="甲乙", span=SourceSpan(3, 4), rule_source="rule",
        change_id="real-change", file_id="with-change",
    )
    with_change = _planned(
        "with-change", "Text/with-change.xhtml", source,
        (Diagnostic("INLINE_BOUNDARY", "boundary", SourceSpan(4, 8)),),
        (change,),
    )
    without_change = _planned(
        "without-change", "Text/without-change.xhtml", "plain",
        (Diagnostic("QUOTE_UNBALANCED", "unbalanced"),),
    )
    preview = PreviewSession(with_change.plan)
    preview.accept_this("real-change")
    dialog = _PreviewDialog(
        make_with_table(), (with_change, without_change), (preview,),
        Translator("en"), None,
    )
    panel = dialog.diagnostic_panel

    assert panel is not None
    assert panel.table.rowCount() == 2
    panel.file_filter.setCurrentIndex(2)
    assert panel.table.rowCount() == 1
    assert panel._visible_records[0].file_id == "without-change"
    panel.file_filter.setCurrentIndex(0)
    panel.code_filter.setCurrentIndex(1)
    assert panel.table.rowCount() == 1
    panel.file_filter.setCurrentIndex(0)
    panel.code_filter.setCurrentIndex(0)

    # Clicking the matching diagnostic reveals the exact real preview row.
    panel.table.cellClicked.emit(0, 0)

    assert dialog.file_filter.currentData() == "with-change"
    assert dialog._selected_change_identity() == ("with-change", "real-change")
    assert preview.decision("real-change") is PreviewDecision.ACCEPT_THIS
    assert "【<em>】" in panel.context.toPlainText()


def test_zero_change_result_offers_a_diagnostic_view(monkeypatch):
    qt = make_with_table()
    planned = _planned(
        "broken", "Text/broken.xhtml", "bad<source",
        (Diagnostic("SOURCE_INVALID_XHTML", "parser detail", line=2, column=7),),
    )
    events = []

    def exec_dialog(dialog):
        if isinstance(dialog, qt.QMessageBox):
            events.append("result")
            dialog._clicked_button = dialog.buttons[1 if len(events) == 1 else -1]
        else:
            events.append("diagnostics")
            dialog.accept()

    monkeypatch.setattr(preview_window, "load_qt", lambda: qt)
    monkeypatch.setattr(preview_window, "ensure_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(preview_window, "exec_dialog", exec_dialog)

    result = preview_window.show_result(
        status="success", files_scanned=1, files_changed=0,
        accepted_changes=0, skipped_changes=0, return_to_scope=True,
        diagnostic_documents=(planned,), translator=Translator("en"),
    )

    assert result == "close"
    assert events == ["result", "diagnostics", "result"]
    result_box = qt.QMessageBox.instances[-1]
    assert "View diagnostics" in [button.label for button in result_box.buttons]

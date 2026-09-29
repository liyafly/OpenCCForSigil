import random
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


def _linear_diagnostic_records(planned_documents, translator):
    """Original per-diagnostic scan retained as an optimization reference."""

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
        starts = _linear_source_line_starts(source)
        changes = tuple(getattr(plan, "changes", ()) or ())
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
            identity = (file_id, code, span_key)
            if identity in seen:
                continue
            seen.add(identity)

            line = getattr(diagnostic, "line", None)
            column = getattr(diagnostic, "column", None)
            if not (isinstance(line, int) and line > 0
                    and isinstance(column, int) and column > 0):
                line = column = None
                if has_source and start is not None and 0 <= start <= len(source):
                    line, column = preview_window._line_column_for_offset(starts, start)
            if line is None or column is None:
                location = translator.text("preview.diagnostic_position_unavailable")
            else:
                location = translator.text(
                    "preview.invalid_source_location", line=line, column=column)

            related = []
            if start is not None and end is not None and 0 <= start <= end <= len(source):
                for change in changes:
                    change_span = getattr(change, "span", None)
                    change_start = getattr(change_span, "start", None)
                    change_end = getattr(change_span, "end", None)
                    if (getattr(change, "file_id", file_id) != file_id
                            or not isinstance(change_start, int)
                            or not isinstance(change_end, int)):
                        continue
                    if code == "INLINE_BOUNDARY":
                        overlaps = change_end == start or change_start == end
                    else:
                        overlaps = (
                            change_start <= start <= change_end
                            if start == end
                            else change_start < end and start < change_end
                        )
                    if overlaps:
                        related_identity = (file_id, str(getattr(change, "change_id", "")))
                        if related_identity not in related:
                            related.append(related_identity)
            diagnostic_name = translator.text(f"diagnostic.name.{code}", code=code)
            if diagnostic_name == f"diagnostic.name.{code}":
                diagnostic_name = translator.text("diagnostic.name.unknown", code=code)
            records.append(preview_window._DiagnosticRecord(
                file_id=file_id,
                href=href,
                code=code,
                name=diagnostic_name,
                description=preview_window.diagnostic_summary(translator, code, 1),
                location=location,
                excerpt=preview_window._diagnostic_excerpt(
                    source, start, end, line, column, starts),
                related_changes=tuple(related),
            ))
    return tuple(records)


def _linear_source_line_starts(source):
    starts = [0]
    index = 0
    while index < len(source):
        if source[index] == "\r":
            index += 2 if index + 1 < len(source) and source[index + 1] == "\n" else 1
            starts.append(index)
        elif source[index] == "\n":
            index += 1
            starts.append(index)
        else:
            index += 1
    return tuple(starts)


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


def test_source_line_starts_handles_lf_cr_crlf():
    assert preview_window._source_line_starts("a\nb\rc\r\nd\n") == (0, 2, 4, 7, 9)


def test_diagnostic_records_match_linear_reference_for_random_plans():
    rng = random.Random(20260928)
    translators = (Translator("en"), Translator("zh-Hans"), Translator("zh-Hant"))
    plans = []
    codes = ("INLINE_BOUNDARY", "QUOTE_UNBALANCED", "MIXED_SCRIPT")
    for plan_index in range(200):
        source = "".join(rng.choice("甲乙丙丁\r\n") for _ in range(rng.randint(1, 80)))
        file_id = f"chapter-{plan_index}"
        changes = []
        for change_index in range(rng.randint(0, 45)):
            start = rng.randrange(len(source) + 1)
            end = rng.randrange(start, len(source) + 1)
            changes.append(TokenChange(
                source="字", target="字", span=SourceSpan(start, end),
                rule_source="random", change_id=f"change-{rng.randrange(12)}",
                file_id=file_id if rng.random() < 0.85 else "another-file",
            ))

        diagnostics = []
        for _ in range(rng.randint(1, 35)):
            code = rng.choice(codes)
            if rng.random() < 0.22:
                diagnostics.append(Diagnostic(
                    code, "hidden", line=rng.randint(1, 8), column=rng.randint(1, 12)))
                continue
            start = rng.randrange(len(source) + 1)
            end = rng.randrange(start, len(source) + 1)
            if rng.random() < 0.18:
                end = start
            if rng.random() < 0.25:
                diagnostics.append(Diagnostic(
                    code, "hidden", SourceSpan(start, end),
                    line=rng.randint(1, 8), column=rng.randint(1, 12)))
            else:
                diagnostics.append(Diagnostic(code, "hidden", SourceSpan(start, end)))
            if rng.random() < 0.08:
                diagnostics.append(diagnostics[-1])
        plans.append(_planned(file_id, f"Text/{file_id}.xhtml", source, diagnostics, changes))

    for translator in translators:
        assert _diagnostic_records(plans, translator) == _linear_diagnostic_records(
            plans, translator)


def test_diagnostic_records_span_accesses_are_near_linear():
    class CountedChange:
        def __init__(self, index):
            self.file_id = "chapter"
            self.change_id = f"change-{index}"
            self._span = SourceSpan(index * 2, index * 2 + 1)
            self.span_accesses = 0

        @property
        def span(self):
            self.span_accesses += 1
            return self._span

    change_count = 20_000
    diagnostic_count = 2_000
    source = "x" * (change_count * 2 + 1)
    changes = tuple(CountedChange(index) for index in range(change_count))
    diagnostics = tuple(
        Diagnostic("QUOTE_UNBALANCED", "hidden", SourceSpan(index * 20, index * 20 + 1))
        for index in range(diagnostic_count)
    )
    planned = _planned("chapter", "Text/chapter.xhtml", source, diagnostics, changes)

    records = _diagnostic_records((planned,), Translator("en"))

    assert len(records) == diagnostic_count
    span_accesses = sum(change.span_accesses for change in changes)
    assert span_accesses <= 20 * (change_count + diagnostic_count)


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


def test_diagnostics_tab_label_shows_count_before_opening():
    duplicate = Diagnostic("QUOTE_UNBALANCED", "first", SourceSpan(0, 1))
    planned = _planned(
        "chapter", "Text/chapter.xhtml", "甲乙",
        (duplicate, Diagnostic("QUOTE_UNBALANCED", "duplicate", SourceSpan(0, 1)),
         Diagnostic("INLINE_BOUNDARY", "boundary", SourceSpan(1, 2))),
    )
    dialog = _PreviewDialog(
        make_with_table(), (planned,), (PreviewSession(planned.plan),),
        Translator("en"), None,
    )

    tab_labels = [arguments[1] for name, arguments in dialog.detail_tabs.calls
                  if name == "addTab"]

    assert dialog._diagnostic_records is None
    assert tab_labels[-1] == Translator("en").text(
        "preview.diagnostics_count", count=2)


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


def test_zero_width_diagnostic_record_is_localized():
    diagnostic = Diagnostic(
        "REGEX_ZERO_WIDTH_SKIPPED", "rule z: skipped 10 zero-width match(es)")
    planned = _planned("chapter", "Text/chapter.xhtml", "正文不能进入诊断", (diagnostic,))

    for language in ("en", "zh-Hans", "zh-Hant"):
        translator = Translator(language)
        (record,) = _diagnostic_records((planned,), translator)

        assert record.name == translator.text("diagnostic.name.REGEX_ZERO_WIDTH_SKIPPED")
        assert "REGEX_ZERO_WIDTH_SKIPPED" not in record.name
        assert record.description == translator.text("rules.zero_width_skipped", id="z", count=10)
        assert "正文不能进入诊断" not in record.description + record.excerpt


def test_zero_width_diagnostics_keep_one_record_per_rule():
    planned = _planned(
        "chapter", "Text/chapter.xhtml", "source",
        (
            Diagnostic("REGEX_ZERO_WIDTH_SKIPPED", "rule a: skipped 2 zero-width match(es)"),
            Diagnostic("REGEX_ZERO_WIDTH_SKIPPED", "rule b: skipped 3 zero-width match(es)"),
        ),
    )

    records = _diagnostic_records((planned,), Translator("en"))

    assert len(records) == 2
    assert [record.description for record in records] == [
        Translator("en").text("rules.zero_width_skipped", id="a", count=2),
        Translator("en").text("rules.zero_width_skipped", id="b", count=3),
    ]


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

    assert panel is None
    assert dialog._diagnostic_records is None
    dialog._ensure_diagnostics_panel(dialog._diagnostic_tab_index)
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

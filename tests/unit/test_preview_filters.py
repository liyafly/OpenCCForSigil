from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TextTarget, TokenChange
from core.preview import PreviewSession
from tests.support.fake_qt import make_with_table
from tests.unit.test_preview_group_scaling import VisitCountingEntries
from ui.i18n import Translator
from ui import preview_window
from ui.preview_window import _PreviewDialog


def _change(
    change_id, *, file_id="chapter.xhtml", source="原文", target="目标",
    rule_source="UserRule:alpha", category="character", risk="LOW", target_id="",
    group_id="",
):
    return TokenChange(
        source=source, target=target, span=SourceSpan(0, len(source)),
        rule_source=rule_source, change_id=change_id, file_id=file_id,
        category=category, risk=risk, target_id=target_id, group_id=group_id,
    )


def _dialog(changes, *, hrefs=None):
    hrefs = hrefs or {}
    by_file = {}
    for change in changes:
        by_file.setdefault(change.file_id, []).append(change)
    previews = tuple(
        PreviewSession(ConversionPlan(
            source_sha256="", file_id=file_id, changes=tuple(items)))
        for file_id, items in by_file.items()
    )
    planned = tuple(SimpleNamespace(
        source=SimpleNamespace(
            file_id=preview.plan.file_id,
            href=hrefs.get(preview.plan.file_id, preview.plan.file_id),
            document_kind="xhtml",
        ),
        plan=preview.plan,
    ) for preview in previews)
    dialog = _PreviewDialog(make_with_table(), planned, previews, Translator("en"))
    return dialog, previews


def _visible_ids(dialog):
    return tuple(change.change_id for _preview, change in dialog._visible_entries_cache)


def _filter(dialog, name, value):
    combo = getattr(dialog, name)
    combo.setCurrentIndex(combo.findData(value))


def _search(dialog, query):
    dialog.search_input.setText(query)
    dialog._refresh()


def test_search_matches_decoded_source_full_target_rule_and_file_href_case_insensitively():
    changes = (
        _change("source", source="前软&amp;件后"),
        _change("target", target="完整长目标片段-甲乙丙丁-末尾"),
        _change("rule", rule_source="UserRule:CaseSensitiveName"),
        _change("href", file_id="other.xhtml", source="不同"),
    )
    dialog, _ = _dialog(changes, hrefs={"other.xhtml": "Text/Chapter-Appendix.xhtml"})

    _search(dialog, "软&件")
    assert _visible_ids(dialog) == ("source",)
    _search(dialog, "甲乙丙丁-末尾")
    assert _visible_ids(dialog) == ("target",)
    _search(dialog, "casesensitivename")
    assert _visible_ids(dialog) == ("rule",)
    _search(dialog, "chapter-appendix")
    assert _visible_ids(dialog) == ("href",)


def test_blank_search_matches_all_and_search_refresh_is_debounced():
    dialog, _ = _dialog((
        _change("one"), _change("two", source="其它", target="独有目标"),
    ))

    _search(dialog, "   \t ")
    assert _visible_ids(dialog) == ("one", "two")
    assert dialog.filter_count_label.text() == "Visible 2 / 2"
    assert "search_input" not in dialog._ui_preferences

    dialog.search_input.setText("独有")
    dialog.search_input.textChanged.emit("独有")
    assert dialog._search_refresh_timer.isActive()
    assert _visible_ids(dialog) == ("one", "two")
    dialog._search_refresh_timer.timeout.emit()
    assert _visible_ids(dialog) == ("two",)
    dialog._search_refresh_timer.stop()
    assert not dialog._search_refresh_timer.isActive()


def test_source_category_file_status_and_query_combine_with_and_then_clear():
    changes = (
        _change("match", source="needle one"),
        _change("wrong-source", source="needle two", rule_source="UserRule:beta"),
        _change("wrong-file", file_id="other.xhtml", source="needle three"),
        _change("wrong-category", source="needle four", category="punctuation"),
        _change("wrong-risk", source="needle five", risk="HIGH"),
    )
    dialog, previews = _dialog(changes, hrefs={"other.xhtml": "Text/other.xhtml"})

    _filter(dialog, "file_filter", "chapter.xhtml")
    _filter(dialog, "category_filter", "character")
    _filter(dialog, "risk_filter", "LOW")
    _filter(dialog, "source_filter", "UserRule:alpha")
    _filter(dialog, "status_filter", "undecided")
    _search(dialog, "needle")
    assert _visible_ids(dialog) == ("match",)
    assert dialog.source_filter.currentData() == "UserRule:alpha"
    assert dialog.source_filter.currentText() == "User rule — alpha"

    previews[0].accept_this("match")
    _filter(dialog, "status_filter", "accepted")
    assert _visible_ids(dialog) == ("match",)
    _filter(dialog, "status_filter", "undecided")
    assert _visible_ids(dialog) == ()
    assert dialog.detail.toPlainText() == "No changes match these filters."
    assert not dialog.apply_button.isEnabled()

    dialog._clear_filters()
    assert set(_visible_ids(dialog)) == {change.change_id for change in changes}
    assert dialog.search_input.text() == ""
    assert all(getattr(dialog, name).currentData() is None for name in (
        "file_filter", "category_filter", "risk_filter", "source_filter", "status_filter",
    ))


def test_pending_filter_hides_decided_row_preserves_next_identity_and_apply_guard():
    dialog, _previews = _dialog(tuple(_change(f"change-{i}") for i in range(3)))

    _filter(dialog, "status_filter", "undecided")
    dialog._set_current_row(1)
    dialog._accept_this()

    assert _visible_ids(dialog) == ("change-0", "change-2")
    assert dialog._current_entry()[1].change_id == "change-2"
    assert dialog.filter_count_label.text() == "Visible 2 / 3"
    assert not dialog.apply_button.isEnabled()


def test_undecided_filter_accept_updates_only_the_affected_row(monkeypatch):
    dialog, _previews = _dialog(tuple(
        _change(f"change-{index}") for index in range(20_000)
    ))
    _filter(dialog, "status_filter", "undecided")
    dialog._entries = VisitCountingEntries(dialog._entries)
    dialog._set_current_row(500)
    before_count = len(dialog._visible_entries_cache)

    decision_calls = 0
    original_decision = PreviewSession.decision

    def counted_decision(preview, change_id):
        nonlocal decision_calls
        decision_calls += 1
        return original_decision(preview, change_id)

    monkeypatch.setattr(PreviewSession, "decision", counted_decision)
    dialog._accept_this()

    assert decision_calls <= 1_000
    assert dialog._entries.visits <= 1_000
    assert len(dialog._visible_entries_cache) == before_count - 1
    assert dialog._current_entry()[1].change_id == "change-501"
    assert dialog.table_model.removed_ranges[-1] == (500, 500)


def test_undecided_filter_group_accept_does_not_rescan_visible_rows(monkeypatch):
    group_count = 10_000
    changes = tuple(
        _change(
            f"change-{index}", rule_source=f"UserRule:{index // 2}",
            category="user_rule", risk="HIGH", group_id=f"rules:occurrence-{index // 2}",
        )
        for index in range(group_count * 2)
    )
    dialog, _previews = _dialog(changes)
    _filter(dialog, "status_filter", "undecided")

    decision_calls = 0
    total_visible_visits = 0
    original_decision = PreviewSession.decision

    def counted_decision(preview, change_id):
        nonlocal decision_calls
        decision_calls += 1
        return original_decision(preview, change_id)

    monkeypatch.setattr(PreviewSession, "decision", counted_decision)

    for index in range(5):
        visible = VisitCountingEntries(dialog._visible_entries_cache)
        dialog._visible_entries_cache = visible
        before_count = len(visible)
        before_decisions = decision_calls
        dialog._set_current_row(100)
        dialog._accept_this()

        total_visible_visits += visible.visits
        assert visible.visits <= 1_000
        assert decision_calls - before_decisions <= 1_000
        assert len(dialog._visible_entries_cache) == before_count - 2
        assert dialog._current_entry()[1].change_id == f"change-{100 + 2 * (index + 1)}"

    assert total_visible_visits <= 1_000


def test_incremental_row_removal_falls_back_when_model_rejects_range(monkeypatch):
    dialog, _previews = _dialog((_change("first"), _change("second")))
    _filter(dialog, "status_filter", "undecided")
    prior_model_entries = dialog.table_model.rows.entries
    monkeypatch.setattr(
        dialog.table_model, "remove_rows", lambda _ranges: prior_model_entries)
    dialog._set_current_row(0)

    dialog._accept_this()

    assert _visible_ids(dialog) == ("second",)
    assert dialog.table_model.rowCount() == 1
    assert dialog.table_model.rows.entries == dialog._visible_entries_cache


def test_skipped_status_filter_matches_rejected_decisions():
    dialog, previews = _dialog((_change("skipped"), _change("pending", source="另一个")))
    previews[0].reject_this("skipped")

    _filter(dialog, "status_filter", "rejected")

    assert _visible_ids(dialog) == ("skipped",)


def test_empty_preview_and_filter_no_match_have_distinct_messages():
    empty, _ = _dialog(())
    assert empty.detail.toPlainText() == "No conversion changes were found."

    dialog, _ = _dialog((_change("one"),))
    _search(dialog, "not-present")
    assert dialog.detail.toPlainText() == "No changes match these filters."
    assert dialog.filter_count_label.text() == "Visible 0 / 1"


def test_search_is_literal_and_does_not_search_context_or_format_every_row(monkeypatch):
    changes = tuple(
        _change(
            f"change-{index}", source="a.b" if index == 9999 else "ab",
            target="目标", target_id=f"target-{index}",
        )
        for index in range(10_000)
    )
    target = TextTarget(
        node_id="target-0", source_text="needle is only surrounding context",
        source_start=0, source_end=len("needle is only surrounding context"),
    )
    plan = ConversionPlan(
        source_sha256="", file_id="chapter.xhtml", changes=changes, targets=(target,))
    preview = PreviewSession(plan)
    planned = (SimpleNamespace(
        source=SimpleNamespace(
            file_id="chapter.xhtml", href="Text/chapter.xhtml", document_kind="xhtml"),
        plan=plan,
    ),)
    formatted = []
    original = preview_window.format_change_row
    monkeypatch.setattr(
        preview_window, "format_change_row",
        lambda *args, **kwargs: formatted.append(True) or original(*args, **kwargs),
    )
    dialog = _PreviewDialog(make_with_table(), planned, (preview,), Translator("en"))

    _search(dialog, "needle")
    assert _visible_ids(dialog) == ()
    _search(dialog, "a.b")
    assert _visible_ids(dialog) == ("change-9999",)
    assert formatted == []

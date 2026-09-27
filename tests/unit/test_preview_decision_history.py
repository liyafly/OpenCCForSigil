from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewDecision, PreviewError, PreviewSession
from tests.support.fake_qt import make_with_table
from ui import preview_window
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog


def _change(change_id, *, file_id="chapter.xhtml", group_id=None, source="甲"):
    return TokenChange(
        source=source, target=f"乙-{change_id}", span=SourceSpan(0, len(source)),
        rule_source="UserRule:history", change_id=change_id, file_id=file_id,
        category="user_rule", risk="HIGH", group_id=group_id,
    )


def _dialog(changes, *, language="en"):
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
            href=preview.plan.file_id,
            document_kind="xhtml",
        ),
        plan=preview.plan,
    ) for preview in previews)
    return _PreviewDialog(
        make_with_table(), planned, previews, Translator(language)), previews


def _decisions(previews):
    return {
        (change.file_id, change.change_id): preview.decision(change.change_id)
        for preview in previews for change in preview.changes
    }


def test_preview_session_can_restore_a_decision_and_return_to_undecided():
    preview = PreviewSession(ConversionPlan(
        source_sha256="", changes=(_change("one"),)))
    preview.accept_this("one")
    preview.restore_decision("one", None)

    assert preview.decision("one") is None
    assert preview.undecided()[0].change_id == "one"
    preview.restore_decision("one", PreviewDecision.REJECT_THIS)
    assert preview.summary()["rejected"] == 1
    try:
        preview.restore_decision("missing", None)
    except PreviewError:
        pass
    else:
        raise AssertionError("unknown change id must be rejected")


def test_single_decision_undo_redo_and_reset_current_are_one_operation_each():
    dialog, previews = _dialog((_change("one"), _change("two", source="丙")))
    dialog._set_current_row(0)

    dialog._accept_this()
    assert previews[0].decision("one") == PreviewDecision.ACCEPT_THIS
    assert len(dialog._undo_stack) == 1
    dialog._undo_preview_action()
    assert previews[0].decision("one") is None
    assert dialog._totals["undecided"] == 2
    assert len(dialog._redo_stack) == 1
    dialog._redo_preview_action()
    assert previews[0].decision("one") == PreviewDecision.ACCEPT_THIS
    assert dialog._totals["accepted"] == 1

    dialog._set_current_row(0)
    dialog._reset_current_to_undecided()
    assert previews[0].decision("one") is None
    dialog._undo_preview_action()
    assert previews[0].decision("one") == PreviewDecision.ACCEPT_THIS
    dialog._redo_preview_action()
    assert previews[0].decision("one") is None


def test_occurrence_group_accept_reset_undo_and_redo_are_atomic():
    group = "rules:occurrence-1"
    dialog, previews = _dialog((
        _change("one", group_id=group), _change("two", group_id=group, source="丙"),
    ))
    dialog._decide_entry(dialog._entries[0], True)
    assert all(decision == PreviewDecision.ACCEPT_THIS
               for decision in _decisions(previews).values())

    dialog._undo_preview_action()
    assert all(decision is None for decision in _decisions(previews).values())
    dialog._redo_preview_action()
    assert all(decision == PreviewDecision.ACCEPT_THIS
               for decision in _decisions(previews).values())

    dialog._set_current_row(0)
    dialog._reset_current_to_undecided()
    assert all(decision is None for decision in _decisions(previews).values())
    dialog._undo_preview_action()
    assert all(decision == PreviewDecision.ACCEPT_THIS
               for decision in _decisions(previews).values())


def test_file_filter_and_all_operations_can_be_undone_redone_and_new_action_clears_redo():
    dialog, previews = _dialog((
        _change("chapter-1"), _change("chapter-2", source="丙"),
        _change("other-1", file_id="other.xhtml", source="丁"),
    ))
    dialog._accept_file()
    snapshot = _decisions(previews)
    assert snapshot[("chapter.xhtml", "chapter-1")] == PreviewDecision.ACCEPT_THIS
    assert snapshot[("chapter.xhtml", "chapter-2")] == PreviewDecision.ACCEPT_THIS
    assert snapshot[("other.xhtml", "other-1")] is None
    dialog._undo_preview_action()
    assert all(decision is None for decision in _decisions(previews).values())
    dialog._redo_preview_action()
    assert _decisions(previews) == snapshot

    dialog._undo_preview_action()
    dialog._accept_this()
    assert dialog._redo_stack == []
    dialog._accept_all()
    all_accepted = _decisions(previews)
    dialog._undo_preview_action()
    assert _decisions(previews) == {
        ("chapter.xhtml", "chapter-1"): PreviewDecision.ACCEPT_THIS,
        ("chapter.xhtml", "chapter-2"): None,
        ("other.xhtml", "other-1"): None,
    }
    dialog._redo_preview_action()
    assert _decisions(previews) == all_accepted


def test_filtered_decision_undo_restores_status_filter_visibility():
    dialog, previews = _dialog((_change("one"), _change("two", source="丙")))
    dialog.status_filter.setCurrentIndex(dialog.status_filter.findData("undecided"))
    dialog._decide_filtered(True)
    assert all(preview.summary()["accepted"] == 2 for preview in previews)
    assert dialog._visible_entries_cache == ()

    dialog._undo_preview_action()
    assert all(preview.summary()["undecided"] == 2 for preview in previews)
    assert tuple(change.change_id for _preview, change in dialog._visible_entries_cache) == (
        "one", "two")
    dialog._redo_preview_action()
    assert dialog._visible_entries_cache == ()


def test_cross_file_language_group_current_file_action_undoes_as_one_change():
    dialog, previews = _dialog((
        _change("chapter-lang", file_id="chapter.xhtml", group_id="language_metadata"),
        _change("opf-lang", file_id="content.opf", group_id="language_metadata"),
    ))
    dialog._decide_current_file_groups(True)

    assert all(preview.summary()["accepted"] == 1 for preview in previews)
    dialog._undo_preview_action()
    assert all(preview.summary()["undecided"] == 1 for preview in previews)
    dialog._redo_preview_action()
    assert all(preview.summary()["accepted"] == 1 for preview in previews)


def test_history_operation_and_record_limits_evict_whole_oldest_operations(monkeypatch):
    monkeypatch.setattr(preview_window, "_MAX_DECISION_HISTORY_OPERATIONS", 2)
    dialog, previews = _dialog(tuple(_change(f"change-{i}") for i in range(3)))
    for row in range(3):
        dialog._set_current_row(row)
        dialog._accept_this()
    assert len(dialog._undo_stack) == 2
    dialog._undo_preview_action()
    dialog._undo_preview_action()
    assert _decisions(previews)[("chapter.xhtml", "change-0")] == PreviewDecision.ACCEPT_THIS
    assert _decisions(previews)[("chapter.xhtml", "change-1")] is None
    assert _decisions(previews)[("chapter.xhtml", "change-2")] is None

    monkeypatch.setattr(preview_window, "_MAX_DECISION_HISTORY_CHANGES", 2)
    oversized, previews = _dialog(tuple(_change(f"big-{i}") for i in range(3)))
    oversized._accept_this()
    oversized._reject_all()
    assert len(oversized._undo_stack) == 1
    assert len(oversized._undo_stack[0].changes) == 3
    assert "history limit" in oversized._history_feedback.lower()
    oversized._undo_preview_action()
    assert _decisions(previews)[("chapter.xhtml", "big-0")] == PreviewDecision.ACCEPT_THIS
    assert _decisions(previews)[("chapter.xhtml", "big-1")] is None
    assert _decisions(previews)[("chapter.xhtml", "big-2")] is None


def test_history_clears_only_after_exit_is_confirmed_or_apply_succeeds():
    dialog, previews = _dialog((_change("one"),))
    dialog._accept_this()
    dialog._confirm_discard_decisions = lambda: False
    assert dialog._guard_reject() is False
    assert dialog._undo_stack

    dialog._confirm_discard_decisions = lambda: True
    assert dialog._guard_reject() is True
    assert not dialog._undo_stack and not dialog._redo_stack

    applying, previews = _dialog((_change("apply"),))
    applying._accept_all()
    applying._checkpoint_confirm = lambda: True
    applying._apply()
    assert applying.applied
    assert not applying._undo_stack and not applying._redo_stack


def test_decision_shortcuts_are_scoped_to_table_not_search_or_detail_widgets():
    dialog, _ = _dialog((_change("one"),))

    assert dialog._shortcuts
    assert all(shortcut.args[1] is dialog.table_view for shortcut in dialog._shortcuts)
    assert all(("setContext", (1,)) in shortcut.calls for shortcut in dialog._shortcuts)
    assert dialog.search_input is not dialog.table_view

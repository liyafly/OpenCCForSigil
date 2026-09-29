import re
from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewDecision, PreviewSession
from ui.preview_batch import plan_batch_decision
from collections import namedtuple


def _entries(specs):
    by_file = {}
    for change_id, file_id, group_id in specs:
        by_file.setdefault(file_id, []).append(TokenChange(
            source="src", target="dst", span=SourceSpan(0, 3),
            rule_source="rule", change_id=change_id, file_id=file_id,
            group_id=group_id,
        ))
    sessions = tuple(PreviewSession(ConversionPlan(
        source_sha256="", file_id=file_id, changes=tuple(changes)))
        for file_id, changes in by_file.items())
    entries = tuple((session, change) for session in sessions for change in session.changes)
    group_entries = {}
    group_files = {}
    for entry in entries:
        change = entry[1]
        if change.group_id:
            group_entries.setdefault(change.group_id, []).append(entry)
            group_files.setdefault(change.group_id, set()).add(change.file_id)
    return entries, sessions, group_entries, {
        key: frozenset(value) for key, value in group_files.items()
    }


def _plan(entries, groups, group_files, **kwargs):
    return plan_batch_decision(entries, groups, group_files, **kwargs)


def test_b1_only_undecided_default_preserves_manual_accepts_and_skips():
    entries, sessions, groups, group_files = _entries(
        [(f"c{i}", "book", None) for i in range(10)])
    for preview, change in entries[:2]:
        preview.accept_this(change.change_id)
    for preview, change in entries[2:5]:
        preview.reject_this(change.change_id)
    identities = {(change.file_id, change.change_id) for _, change in entries}

    plan = _plan(entries, groups, group_files, visible_identities=identities)

    assert plan.change_count == 5
    assert plan.overwrite_count == 0
    for preview, change in plan.entries:
        preview.accept_this(change.change_id)
    assert [preview.finalize().changes for preview in sessions]
    assert sum(preview.decision(change.change_id) in {
        PreviewDecision.ACCEPT_THIS, PreviewDecision.ACCEPT_ALL}
        for preview, change in entries) == 7
    assert sum(preview.decision(change.change_id) is PreviewDecision.REJECT_THIS
               for preview, change in entries) == 3


def test_resolve_remaining_preserves_manual_skips(monkeypatch):
    from types import SimpleNamespace

    from tests.support.fake_qt import make_with_table
    from ui import preview_window
    from ui.i18n import Translator
    from ui.preview_window import _PreviewDialog

    entries, sessions, _groups, _group_files = _entries(
        [(f"c{i}", "book", None) for i in range(10)])
    for preview, change in entries[:2]:
        preview.accept_this(change.change_id)
    for preview, change in entries[2:5]:
        preview.reject_this(change.change_id)
    planned = (SimpleNamespace(
        source=SimpleNamespace(
            file_id="book", href="Text/book.xhtml", document_kind="xhtml"),
        plan=sessions[0].plan,
    ),)
    dialog = _PreviewDialog(
        make_with_table(), planned, sessions, Translator("en"), None)

    def confirm_batch(batch_dialog):
        children = batch_dialog._layout.children
        form = next(item for item in children if isinstance(item, dialog._qt.QFormLayout))
        scope_label, scope_combo = form.children[0]
        action_label, action_combo = form.children[1]
        only_check = next(item for item in children if isinstance(item, dialog._qt.QCheckBox))
        summary = children[2]
        confirm = children[-1].children[-1]

        assert scope_label.text() == "Scope"
        assert action_label.text() == "Action"
        assert scope_combo.currentData() == "all"
        assert action_combo.currentData() == "accept"
        assert only_check.isChecked()
        assert summary.text() == "Will accept 5 changes in one file."
        assert "0" not in summary.text()

        only_check.setChecked(False)
        assert "Existing decisions to replace: 3." in summary.text()
        assert confirm.text() == "Confirm and overwrite 3 decisions (8 changes)"
        only_check.setChecked(True)
        return 1

    monkeypatch.setattr(preview_window, "exec_dialog", confirm_batch)
    dialog._open_batch_decision(initial_scope="all")

    assert sum(preview.decision(change.change_id) is PreviewDecision.ACCEPT_THIS
               for preview, change in entries) == 7
    assert sum(preview.decision(change.change_id) is PreviewDecision.REJECT_THIS
               for preview, change in entries) == 3
    assert len(dialog._undo_stack) == 1


def test_batch_feedback_omits_zero_groups(monkeypatch):
    from types import SimpleNamespace

    from tests.support.fake_qt import make_with_table
    from ui import preview_window
    from ui.i18n import Translator
    from ui.preview_window import _PreviewDialog

    entries, sessions, _groups, _group_files = _entries(
        [(f"c{i}", "book", None) for i in range(10)])
    for preview, change in entries[:2]:
        preview.accept_this(change.change_id)
    for preview, change in entries[2:5]:
        preview.reject_this(change.change_id)
    planned = (SimpleNamespace(
        source=SimpleNamespace(
            file_id="book", href="Text/book.xhtml", document_kind="xhtml"),
        plan=sessions[0].plan,
    ),)
    translator = Translator("en")
    dialog = _PreviewDialog(make_with_table(), planned, sessions, translator, None)
    monkeypatch.setattr(preview_window, "exec_dialog", lambda _dialog: 1)

    dialog._open_batch_decision(initial_scope="all")

    assert dialog._last_group_feedback == translator.text(
        "preview.batch_applied_main", changes=5)
    assert re.search(r"(?<![\d.])0(?!\d)", dialog._last_group_feedback) is None


def test_b2_explicit_overwrite_changes_eight_and_counts_three_overrides():
    entries, _sessions, groups, group_files = _entries(
        [(f"c{i}", "book", None) for i in range(10)])
    for preview, change in entries[:2]:
        preview.accept_this(change.change_id)
    for preview, change in entries[2:5]:
        preview.reject_this(change.change_id)

    plan = _plan(entries, groups, group_files, scope="all", undecided_only=False)

    assert plan.change_count == 8
    assert plan.overwrite_count == 3


def test_b3_filter_hit_expands_atomic_group_and_counts_hidden_members():
    entries, _sessions, groups, group_files = _entries([
        ("one", "a", "rules:occurrence"),
        ("two", "b", "rules:occurrence"),
        ("three", "b", "rules:occurrence"),
    ])

    plan = _plan(entries, groups, group_files, visible_identities={("a", "one")})

    assert plan.change_count == 3
    assert plan.group_count == 1
    assert plan.file_count == 2
    assert plan.hidden_count == 2


def test_b4_pending_only_excludes_a_group_with_existing_decisions():
    entries, _sessions, groups, group_files = _entries([
        ("one", "book", "rules:occurrence"),
        ("two", "book", "rules:occurrence"),
        ("three", "book", "rules:occurrence"),
    ])
    entries[0][0].accept_this("one")

    plan = _plan(entries, groups, group_files, scope="all")

    assert plan.change_count == 0
    assert plan.excluded_mixed_groups == 1
    assert plan.excluded_mixed_changes == 2


def test_b5_file_scope_includes_local_rules_and_excludes_language_group():
    entries, _sessions, groups, group_files = _entries([
        ("rule-a", "a", "rules:local"), ("rule-b", "a", "rules:local"),
        ("tag-a", "a", "language_metadata"),
        ("tag-opf", "content.opf", "language_metadata"),
    ])

    file_plan = _plan(entries, groups, group_files, scope="file", file_id="a")
    all_plan = _plan(entries, groups, group_files, scope="all")

    assert file_plan.change_count == 2
    assert file_plan.excluded_language_groups == 1
    assert {change.change_id for _, change in all_plan.entries} == {
        "rule-a", "rule-b", "tag-a", "tag-opf"}


def test_b6_same_rule_id_in_distinct_occurrences_stays_separate():
    entries, _sessions, groups, group_files = _entries([
        ("first", "book", "rules:first-occurrence"),
        ("second", "book", "rules:second-occurrence"),
    ])

    plan = _plan(entries, groups, group_files, visible_identities={("book", "first")})

    assert {change.change_id for _, change in plan.entries} == {"first"}


def test_b7_empty_and_repeating_same_target_plan_no_changes():
    entries, _sessions, groups, group_files = _entries([("one", "book", None)])
    entries[0][0].accept_this("one")

    repeated = _plan(entries, groups, group_files, scope="all", undecided_only=False)
    empty = _plan(entries, groups, group_files, visible_identities=set())

    assert repeated.change_count == 0
    assert empty.change_count == 0


def test_b9_300k_mixed_status_plan_visits_each_entry_once_without_text_payloads():
    change_type = namedtuple("BatchChange", "change_id file_id group_id")

    class CountingPreview:
        plan = type("Plan", (), {"file_id": "book"})()

        def __init__(self):
            self.visits = 0

        def decision(self, change_id):
            self.visits += 1
            return (PreviewDecision.ACCEPT_THIS
                    if int(change_id.rsplit("-", 1)[1]) % 2 == 0 else None)

    preview = CountingPreview()
    count = 300_000
    entries = tuple((preview, change_type(f"change-{index}", "book", None))
                    for index in range(count))

    plan = plan_batch_decision(
        entries, {}, {}, scope="all", undecided_only=True,
    )

    assert plan.change_count == count // 2
    assert preview.visits == count
    assert all(not hasattr(change, "source") and not hasattr(change, "target")
               for _session, change in plan.entries[:10])

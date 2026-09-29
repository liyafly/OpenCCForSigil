from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from tests.support.fake_qt import make_with_table
from tests.support.preview_batch import apply_batch_decision
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog


class VisitCountingEntries:
    def __init__(self, entries):
        self.entries = tuple(entries)
        self.visits = 0

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, index):
        return self.entries[index]

    def __iter__(self):
        for entry in self.entries:
            self.visits += 1
            yield entry


def _grouped_dialog(group_count):
    changes = tuple(
        TokenChange(
            source="旧" if index % 2 == 0 else "甲",
            target="新" if index % 2 == 0 else "乙",
            span=SourceSpan(index * 2, index * 2 + 1),
            rule_source=f"UserRule:{index // 2}",
            change_id=f"change-{index}", file_id="chapter.xhtml",
            category="user_rule", risk="HIGH",
            group_id=f"rules:occurrence-{index // 2}",
        )
        for index in range(group_count * 2)
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=changes))
    plan = preview.plan
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter.xhtml", href="Text/chapter.xhtml",
                               document_kind="xhtml"),
        plan=plan,
    ),)
    dialog = _PreviewDialog(make_with_table(), planned, (preview,), Translator("en"))
    dialog._entries = VisitCountingEntries(dialog._entries)
    dialog._refresh = lambda **_kwargs: None
    return dialog, preview


def test_batch_deciding_two_thousand_rule_groups_scans_the_preview_linearly(monkeypatch):
    group_count = 2_000
    dialog, preview = _grouped_dialog(group_count)

    apply_batch_decision(monkeypatch, dialog, scope="filtered")

    assert preview.summary() == {
        "total": group_count * 2,
        "accepted": group_count * 2,
        "rejected": 0,
        "undecided": 0,
    }
    assert dialog._entries.visits <= 10 * len(dialog._entries)


def test_deciding_one_occurrence_does_not_visit_unrelated_preview_entries():
    dialog, preview = _grouped_dialog(1_000)
    before = dialog._entries.visits

    count = dialog._decide_group("rules:occurrence-500", True)

    assert count == 2
    assert dialog._entries.visits - before <= 2
    assert preview.decision("change-1000").value == "accept_this"
    assert preview.decision("change-1001").value == "accept_this"
    assert preview.decision("change-0") is None


def test_file_batch_visits_only_that_file_and_incremental_counts_match_recompute(
    monkeypatch,
):
    file_count = 100
    changes_per_file = 200
    previews = []
    planned = []
    for file_index in range(file_count):
        file_id = f"chapter-{file_index}.xhtml"
        changes = tuple(
            TokenChange(
                source="旧", target="新",
                span=SourceSpan(change_index * 2, change_index * 2 + 1),
                rule_source="UserRule:alpha",
                change_id=f"{file_index}-{change_index}", file_id=file_id,
                category="user_rule", risk="HIGH",
            )
            for change_index in range(changes_per_file)
        )
        preview = PreviewSession(ConversionPlan(
            source_sha256="", file_id=file_id, changes=changes))
        previews.append(preview)
        planned.append(SimpleNamespace(
            source=SimpleNamespace(
                file_id=file_id, href=f"Text/{file_id}", document_kind="xhtml"),
            plan=preview.plan,
        ))
    dialog = _PreviewDialog(
        make_with_table(), tuple(planned), tuple(previews), Translator("en"))
    dialog._entries = VisitCountingEntries(dialog._entries)
    dialog._entries_by_file["chapter-0.xhtml"] = VisitCountingEntries(
        dialog._entries_by_file["chapter-0.xhtml"])
    decision_calls = 0
    original_decision = PreviewSession.decision

    def counted_decision(preview, change_id):
        nonlocal decision_calls
        decision_calls += 1
        return original_decision(preview, change_id)

    monkeypatch.setattr(PreviewSession, "decision", counted_decision)
    dialog._set_current_row(0)
    apply_batch_decision(monkeypatch, dialog, scope="file")

    assert decision_calls <= 10_000
    assert dialog._entries_by_file["chapter-0.xhtml"].visits <= 3 * changes_per_file + 50
    assert dialog._totals == {
        "total": file_count * changes_per_file,
        "accepted": changes_per_file,
        "rejected": 0,
        "undecided": (file_count - 1) * changes_per_file,
    }
    incremental_totals = dialog._totals.copy()
    incremental_file_counts = dialog._file_filter_counts.copy()
    incremental_accepted_by_file = dialog._accepted_count_by_file.copy()

    dialog._recompute_counts()

    assert dialog._totals == incremental_totals
    assert dialog._file_filter_counts == incremental_file_counts
    assert dialog._accepted_count_by_file == incremental_accepted_by_file

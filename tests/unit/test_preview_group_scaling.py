from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from tests.support.fake_qt import make_with_table
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


def test_bulk_deciding_two_thousand_rule_groups_scans_the_preview_linearly():
    group_count = 2_000
    dialog, preview = _grouped_dialog(group_count)

    dialog._decide_filtered(True)

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

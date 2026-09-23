from core.models import ConversionPlan, Diagnostic, SourceSpan, TokenChange
from core.preview import PreviewSession
from ui.preview_window import _PreviewDialog, _guarded_preview_dialog, _translator


class _FakeItem:
    def __init__(self, text: str) -> None:
        self.text = text
        self.set_calls = 0

    def setText(self, text: str) -> None:
        self.text = text
        self.set_calls += 1


class _FakeListWidget:
    def __init__(self, items: list[_FakeItem], current_row: int) -> None:
        self.items = items
        self.current_row = current_row

    def currentRow(self) -> int:
        return self.current_row

    def item(self, row: int) -> _FakeItem | None:
        return self.items[row] if 0 <= row < len(self.items) else None


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


class _FakeButton:
    def __init__(self) -> None:
        self.enabled = None

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


class _FakeDetail:
    def __init__(self) -> None:
        self.text = ""

    def setPlainText(self, text: str) -> None:
        self.text = text

    def clear(self) -> None:
        self.text = ""


class _FakeDialog:
    def __init__(self) -> None:
        self.accept_calls = 0
        self.reject_calls = 0

    def accept(self) -> None:
        self.accept_calls += 1

    def reject(self) -> None:
        self.reject_calls += 1


class _FakeCombo:
    def __init__(self, value=None) -> None:
        self.value = value

    def currentData(self):
        return self.value


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
    entries = tuple((preview, change) for change in preview.changes)
    items = [_FakeItem(_PreviewDialog._entry_text(preview, change)) for _, change in entries]

    dialog = object.__new__(_PreviewDialog)
    dialog._previews = (preview,)
    dialog._entries = entries
    dialog.applied = False
    dialog.back_to_settings = False
    dialog._allow_reject = False
    dialog.list_widget = _FakeListWidget(items, current_row)
    dialog.summary = _FakeLabel()
    dialog.detail = _FakeDetail()
    for name in (
        "accept_this_button",
        "reject_this_button",
        "accept_file_button",
        "reject_file_button",
        "accept_all_button",
        "reject_all_button",
        "apply_button",
    ):
        setattr(dialog, name, _FakeButton())
    dialog.dialog = _FakeDialog()
    dialog._qt = object()
    return dialog, preview, items


def test_preview_dialog_single_decisions_update_only_selected_row_and_summary():
    _translator.set_language("en")
    dialog, preview, items = _preview_dialog()

    dialog._accept_this()
    assert dialog.list_widget.currentRow() == 1
    assert items[0].set_calls == 0
    assert items[1].set_calls == 1
    assert items[2].set_calls == 0
    assert items[1].text.startswith("✓ ")
    assert "Accepted: 1" in dialog.summary.text
    assert "Undecided: 2" in dialog.summary.text
    assert "丁" in dialog.detail.text
    assert dialog.apply_button.enabled is False

    dialog.list_widget.current_row = 2
    dialog._reject_this()
    assert dialog.list_widget.currentRow() == 2
    assert items[0].set_calls == 0
    assert items[1].set_calls == 1
    assert items[2].set_calls == 1
    assert items[2].text.startswith("× ")
    assert "Accepted: 1" in dialog.summary.text
    assert "Skipped: 1" in dialog.summary.text
    assert "Undecided: 1" in dialog.summary.text
    assert "己" in dialog.detail.text


def test_preview_dialog_apply_blocks_undecided_and_accepts_decided_without_finalizing():
    _translator.set_language("en")
    dialog, preview, _items = _preview_dialog(change_count=2, current_row=0)
    finalize_calls = []
    preview.finalize = lambda: finalize_calls.append(True)

    dialog._apply()
    assert dialog.applied is False
    assert dialog.dialog.accept_calls == 0
    assert finalize_calls == []
    assert dialog.apply_button.enabled is False

    dialog._accept_this()
    dialog.list_widget.current_row = 1
    dialog._reject_this()
    assert dialog.apply_button.enabled is True

    dialog._apply()
    assert dialog.applied is True
    assert dialog.dialog.accept_calls == 1
    assert finalize_calls == []
    assert dialog.apply_button.enabled is False

    dialog._apply()
    assert dialog.dialog.accept_calls == 1


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
    dialog = object.__new__(_PreviewDialog)
    dialog._previews = (first, second)
    dialog._entries = tuple((preview, change) for preview in dialog._previews for change in preview.changes)
    dialog.file_filter = _FakeCombo("chapter.xhtml")
    dialog._refresh = lambda: None
    dialog._decide_filtered(True)

    assert first.decision("language-visible").value == "accept_this"
    assert second.decision("language-hidden").value == "accept_this"
    assert first.decision("character-visible").value == "accept_this"


def test_preview_row_truncates_long_text_but_detail_keeps_full_text():
    source = "前" * 300
    change = TokenChange(
        source=source, target="後" * 300, span=SourceSpan(0, 300),
        rule_source="OpenCC:s2t", change_id="long", file_id="chapter.xhtml",
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(change,)))
    row = _PreviewDialog._entry_text(preview, change)

    assert len(row) < 220
    assert source not in row
    assert "…" in row


def test_plan_diagnostics_are_visible_in_summary_and_detail():
    change = TokenChange(
        source="后", target="後", span=SourceSpan(0, 1), rule_source="OpenCC:s2t",
        change_id="diagnostic", file_id="chapter.xhtml",
    )
    preview = PreviewSession(ConversionPlan(source_sha256="", changes=(change,)))
    dialog = object.__new__(_PreviewDialog)
    dialog._previews = (preview,)
    dialog._entries = ((preview, change),)
    dialog._planned = (
        type("Planned", (), {"plan": ConversionPlan(
            source_sha256="", file_id="chapter.xhtml", diagnostics=(
                Diagnostic("MIXED_SCRIPT", "mixed script input"),
                Diagnostic("INLINE_BOUNDARY", "inline boundary"),
            ),
        )})(),
    )
    dialog.list_widget = _FakeListWidget([_FakeItem("row")], 0)
    dialog.summary = _FakeLabel()
    dialog.detail = _FakeDetail()
    dialog.apply_button = _FakeButton()

    dialog._update_summary()
    dialog._show_current(0)

    assert "MIXED_SCRIPT" in dialog.summary.text
    assert "INLINE_BOUNDARY" in dialog.summary.text
    assert "MIXED_SCRIPT" in dialog.detail.text
    assert "mixed script input" in dialog.detail.text


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

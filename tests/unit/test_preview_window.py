from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from ui.preview_window import _PreviewDialog, _translator


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

    def accept(self) -> None:
        self.accept_calls += 1


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

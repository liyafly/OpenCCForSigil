"""Minimal Preview UI for the first interactive conversion phase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

from core.preview import PreviewError, PreviewSession
from core.workflow import PlannedDocument
from opencc_backend.configs import (
    BASE_CONFIG_BY_JIEBA,
    JIEBA_CONFIG_BY_BASE,
    V1_CONFIGS,
)


class UIUnavailableError(RuntimeError):
    """Raised when Sigil's bundled Qt runtime cannot be imported."""


@dataclass(frozen=True)
class PreviewOutcome:
    accepted: bool
    previews: Tuple[PreviewSession, ...]


CONVERSION_LABELS = {
    "s2t": "简体 → 通用繁体 (s2t)",
    "s2tw": "简体 → 台湾繁体字形 (s2tw)",
    "s2twp": "简体 → 台湾繁体 + 台湾词汇 (s2twp)",
    "s2hk": "简体 → 香港繁体字形 (s2hk)",
    "s2hkp": "简体 → 香港繁体 + 香港词汇 (s2hkp)",
    "t2s": "通用繁体 → 简体 (t2s)",
    "tw2s": "台湾繁体 → 简体字形 (tw2s)",
    "tw2sp": "台湾繁体 → 简体 + 词汇 (tw2sp)",
    "hk2s": "香港繁体 → 简体字形 (hk2s)",
    "hk2sp": "香港繁体 → 简体 + 词汇 (hk2sp)",
    "t2tw": "通用繁体 → 台湾繁体 (t2tw)",
    "t2hk": "通用繁体 → 香港繁体 (t2hk)",
    "tw2t": "台湾繁体 → 通用繁体 (tw2t)",
    "hk2t": "香港繁体 → 通用繁体 (hk2t)",
    "t2jp": "繁体 → 日文新字体 (t2jp)",
    "jp2t": "日文新字体 → 通用繁体 (jp2t)",
}
CONFIG_SELECTION_ORDER = tuple(config for config in V1_CONFIGS if config in CONVERSION_LABELS)


def choose_conversion_config(
    available_configs: Sequence[str],
    *,
    default_config: str = "s2t",
) -> str | None:
    """Ask for an explicit conversion direction before building a plan.

    This selector exposes pinned upstream standard configs and, when the
    selected payload proves the official native plugin is present, an advanced
    Jieba checkbox. The selected concrete config is frozen into the plan.
    """

    qt_widgets = _load_qt_widgets()
    available = set(available_configs)
    configs = tuple(config for config in CONFIG_SELECTION_ORDER if config in available)
    if not configs:
        raise UIUnavailableError(
            "no supported standard OpenCC config is available in the selected payload"
        )

    application = qt_widgets.QApplication.instance()
    owns_application = application is None
    if application is None:
        import sys

        application = qt_widgets.QApplication(sys.argv)
    jieba_configs = {
        base: plugin
        for base, plugin in JIEBA_CONFIG_BY_BASE.items()
        if plugin in available
    }
    dialog = _ConversionConfigDialog(qt_widgets, configs, default_config, jieba_configs)
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    if owns_application:
        application.quit()
    return dialog.selected_config if dialog.accepted else None


def show_preview(planned: Sequence[PlannedDocument]) -> PreviewOutcome:
    """Show a preview and return the sessions containing user decisions."""

    qt_widgets = _load_qt_widgets()
    previews = tuple(PreviewSession(item.plan) for item in planned)
    application = qt_widgets.QApplication.instance()
    owns_application = application is None
    if application is None:
        import sys

        application = qt_widgets.QApplication(sys.argv)
    dialog = _PreviewDialog(qt_widgets, planned, previews)
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    if owns_application:
        application.quit()
    return PreviewOutcome(accepted=dialog.applied, previews=previews)


def _load_qt_widgets() -> Any:
    try:
        from PySide6 import QtWidgets

        return QtWidgets
    except ImportError:
        try:
            from PyQt5 import QtWidgets

            return QtWidgets
        except ImportError as exc:
            raise UIUnavailableError("Sigil bundled Qt runtime is unavailable") from exc


class _PreviewDialog:
    def __init__(self, qt_widgets: Any, planned, previews: Tuple[PreviewSession, ...]) -> None:
        self._qt = qt_widgets
        self._planned = planned
        self._previews = previews
        self._entries: List[Tuple[PreviewSession, str]] = []
        self.applied = False

        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle("OpenCCForSigil Preview")
        self.dialog.resize(900, 620)
        self._build()
        self._refresh()

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)

        self.summary = qt.QLabel()
        layout.addWidget(self.summary)

        self.list_widget = qt.QListWidget()
        self.list_widget.currentRowChanged.connect(self._show_current)
        layout.addWidget(self.list_widget)

        self.detail = qt.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(150)
        layout.addWidget(self.detail)

        buttons = qt.QHBoxLayout()
        self.accept_this_button = qt.QPushButton("Accept this")
        self.reject_this_button = qt.QPushButton("Skip this")
        self.accept_all_button = qt.QPushButton("Accept all")
        self.reject_all_button = qt.QPushButton("Skip all")
        self.apply_button = qt.QPushButton("Apply accepted changes")
        self.cancel_button = qt.QPushButton("Cancel")
        for button in (
            self.accept_this_button,
            self.reject_this_button,
            self.accept_all_button,
            self.reject_all_button,
            self.apply_button,
            self.cancel_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.accept_this_button.clicked.connect(self._accept_this)
        self.reject_this_button.clicked.connect(self._reject_this)
        self.accept_all_button.clicked.connect(self._accept_all)
        self.reject_all_button.clicked.connect(self._reject_all)
        self.apply_button.clicked.connect(self._apply)
        self.cancel_button.clicked.connect(self.dialog.reject)

    def _refresh(self) -> None:
        self._entries = [
            (preview, change.change_id)
            for preview in self._previews
            for change in preview.changes
        ]
        current_row = self.list_widget.currentRow()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for preview, change_id in self._entries:
            change = next(item for item in preview.changes if item.change_id == change_id)
            decision = preview.decision(change_id)
            prefix = "?" if decision is None else "✓" if decision.value.startswith("accept") else "×"
            text = f"{prefix} {change.file_id}: {change.source!r} → {change.target!r}"
            self.list_widget.addItem(text)
        self.list_widget.blockSignals(False)

        if self._entries:
            row = current_row if 0 <= current_row < len(self._entries) else 0
            self.list_widget.setCurrentRow(row)
        else:
            self.detail.setPlainText("No conversion changes were found.")
        self._update_summary()

    def _update_summary(self) -> None:
        totals = {"total": 0, "accepted": 0, "rejected": 0, "undecided": 0}
        for preview in self._previews:
            for key, value in preview.summary().items():
                totals[key] += value
        self.summary.setText(
            "Changes: {total}   Accepted: {accepted}   Skipped: {rejected}   "
            "Undecided: {undecided}".format(**totals)
        )
        has_current = bool(self._entries)
        self.accept_this_button.setEnabled(has_current)
        self.reject_this_button.setEnabled(has_current)
        self.accept_all_button.setEnabled(totals["undecided"] > 0)
        self.reject_all_button.setEnabled(totals["undecided"] > 0)

    def _show_current(self, row: int) -> None:
        if row < 0 or row >= len(self._entries):
            self.detail.clear()
            return
        preview, change_id = self._entries[row]
        change = next(item for item in preview.changes if item.change_id == change_id)
        self.detail.setPlainText(
            f"Rule: {change.rule_source}\n"
            f"Category: {change.category}    Risk: {change.risk}\n"
            f"Before: {change.context_before}{change.source}{change.context_after}\n"
            f"Change: {change.source!r} → {change.target!r}"
        )

    def _current_entry(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def _accept_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].accept_this(entry[1])
        self._refresh()

    def _reject_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].reject_this(entry[1])
        self._refresh()

    def _accept_all(self) -> None:
        for preview in self._previews:
            preview.accept_all()
        self._refresh()

    def _reject_all(self) -> None:
        for preview in self._previews:
            preview.reject_all()
        self._refresh()

    def _apply(self) -> None:
        try:
            for preview in self._previews:
                preview.finalize()
        except PreviewError as exc:
            self._qt.QMessageBox.warning(self.dialog, "Preview incomplete", str(exc))
            return
        self.applied = True
        self.dialog.accept()


class _ConversionConfigDialog:
    def __init__(
        self,
        qt_widgets: Any,
        configs: Tuple[str, ...],
        default_config: str,
        jieba_configs: dict[str, str],
    ) -> None:
        self._qt = qt_widgets
        self._jieba_configs = jieba_configs
        self.accepted = False
        self.selected_config = None
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle("OpenCCForSigil Conversion Direction")
        self.dialog.setMinimumWidth(460)

        layout = qt_widgets.QVBoxLayout(self.dialog)
        label = qt_widgets.QLabel(
            "Choose the conversion direction explicitly. OpenCCForSigil will not "
            "guess or silently reverse it."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self.combo = qt_widgets.QComboBox()
        for config in configs:
            self.combo.addItem(CONVERSION_LABELS[config], config)
        layout.addWidget(self.combo)

        self.jieba_status = qt_widgets.QLabel()
        self.jieba_status.setWordWrap(True)
        layout.addWidget(self.jieba_status)
        self.jieba_checkbox = qt_widgets.QCheckBox(
            "高级：使用官方 native Jieba 分词插件"
        )
        self.jieba_checkbox.setToolTip(
            "只使用当前 vendor payload 中经过哈希校验的官方 opencc-jieba 插件。"
        )
        layout.addWidget(self.jieba_checkbox)

        buttons = qt_widgets.QHBoxLayout()
        self.cancel_button = qt_widgets.QPushButton("Cancel")
        self.continue_button = qt_widgets.QPushButton("Continue to Preview")
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.continue_button)
        layout.addLayout(buttons)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.continue_button.clicked.connect(self._accept)
        self.combo.currentIndexChanged.connect(self._update_jieba_state)
        default_base = BASE_CONFIG_BY_JIEBA.get(default_config, default_config)
        selected_index = self.combo.findData(default_base)
        if selected_index >= 0:
            self.combo.setCurrentIndex(selected_index)
        self.jieba_checkbox.setChecked(default_config in self._jieba_configs.values())
        self._update_jieba_state()

    def _update_jieba_state(self) -> None:
        base_config = str(self.combo.currentData())
        plugin_config = self._jieba_configs.get(base_config)
        if plugin_config is None:
            self.jieba_checkbox.setChecked(False)
            self.jieba_checkbox.setEnabled(False)
        else:
            self.jieba_checkbox.setEnabled(True)
        if self._jieba_configs:
            self.jieba_status.setText(
                "已检测到官方 native opencc-jieba payload；仅支持对应的官方 Jieba config。"
            )
        else:
            self.jieba_status.setText(
                "未检测到官方 native opencc-jieba payload；当前仅提供标准 OpenCC config。"
            )

    def _accept(self) -> None:
        base_config = str(self.combo.currentData())
        self.selected_config = (
            self._jieba_configs[base_config]
            if self.jieba_checkbox.isChecked() and base_config in self._jieba_configs
            else base_config
        )
        self.accepted = True
        self.dialog.accept()

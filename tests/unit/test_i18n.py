import ast
from pathlib import Path
import re
from types import SimpleNamespace

from ui.i18n import (
    Translator,
    choose_language,
    configuration_label,
    diagnostic_summary,
    load_catalogs,
    normalize_language,
    profile_display_name,
    rule_validation_message,
    settings_error_message,
    show_error_details,
)
from ui import preview_window, qt as qt_helpers
from ui.qt import ask_confirmation
from opencc_backend.configs import V1_CONFIGS


_TEXT_ARGUMENTS = {
    "QLabel": (0,), "QPushButton": (0,), "QCheckBox": (0,),
    "QGroupBox": (0,), "QRadioButton": (0,), "QAction": (0,), "QToolButton": (0,),
    "QMenu": (0,), "QTableWidgetItem": (0,), "QListWidgetItem": (0,),
    "setText": (0,), "setPlainText": (0,), "setWindowTitle": (0,),
    "setToolTip": (0,), "setPlaceholderText": (0,), "setStatusTip": (0,),
    "setTitle": (0,), "setDetailedText": (0,), "setInformativeText": (0,),
    "showMessage": (0,), "addAction": (0,), "addMenu": (0,), "addButton": (0,),
    "addRow": (0,), "warning": (1, 2), "information": (1, 2),
    "critical": (1, 2), "question": (1, 2), "getText": (1, 2), "getItem": (1, 2),
}


def _contains_hardcoded_words(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        text = "".join(
            value.value for value in node.values if isinstance(value, ast.Constant)
        )
    elif isinstance(node, ast.BinOp):
        return _contains_hardcoded_words(node.left) or _contains_hardcoded_words(node.right)
    else:
        return False
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", text))


def test_qt_text_arguments_use_translation_catalogs():
    root = Path(preview_window.__file__).parents[1]
    paths = sorted((root / "ui").glob("*.py")) + [root / "app/settings.py"]
    failures = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else None
            for index in _TEXT_ARGUMENTS.get(name, ()):
                if index < len(node.args) and _contains_hardcoded_words(node.args[index]):
                    failures.append(f"{path.name}:{node.lineno}: {name}")
    assert failures == []


def test_supported_catalogs_have_same_keys_and_render_placeholders():
    catalogs = load_catalogs()
    assert set(catalogs) == {"zh-Hans", "en", "zh-Hant"}
    expected = set(catalogs["en"])
    assert all(set(catalog) == expected for catalog in catalogs.values())
    for language in catalogs:
        text = Translator(language).text("scope.selected_count", selected=2, total=8)
        assert "2" in text and "8" in text
        detail = Translator(language).text("preview.change")
        assert detail and detail != "preview.change"
        progress = Translator(language).text("progress.status", phase=Translator(language).text("progress.phase.analyzing"), index=1, total=2, file="a.xhtml")
        assert "a.xhtml" in progress


def test_traditional_chinese_separates_accepting_changes_from_applying_them():
    catalog = load_catalogs()["zh-Hant"]

    assert all(
        "套用" not in value
        for key, value in catalog.items()
        if "accept" in key
    )
    assert "已寫入" in catalog["result.row.written"]
    assert "套用" in catalog["preview.apply"]


def test_locale_mapping_and_preference_precedence():
    assert normalize_language("zh_TW") == "zh-Hant"
    assert normalize_language("zh-CN") == "zh-Hans"
    assert choose_language("zh-Hant", "en", "en-US") == "zh-Hant"
    assert choose_language(None, "zh-TW", "en-US") == "zh-Hant"
    assert choose_language(None, None, "de-DE") == "en"


def test_ui_strings_live_in_the_three_catalogs_and_cover_configs_and_diagnostics():
    catalogs = load_catalogs()
    ui_root = Path(preview_window.__file__).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in ui_root.glob("*.py"))
    for private_table in ("_LOCAL_TEXT", "_LABELS", "_LOCAL_CATALOGS", "CONVERSION_LABELS"):
        assert private_table not in source
    for catalog in catalogs.values():
        assert all(f"config.{config}" in catalog for config in V1_CONFIGS)
        assert all(key in catalog for key in (
            "diagnostic.mixed_script",
            "diagnostic.inline_boundary",
            "diagnostic.quote_unbalanced",
            "diagnostic.source_invalid_xhtml",
        ))
        assert all(key in catalog for key in (
            "rules.validation.row_field",
            "rules.validation.row",
            "rules.validation.field",
            "rules.validation.generic",
            "options.region_required",
            "profile.config_unavailable",
            "options.force_pivot_mismatch",
        ))


def test_rule_validation_summary_localizes_row_and_field():
    class Error(ValueError):
        field = "source"
        index = 1

    for language in ("en", "zh-Hans", "zh-Hant"):
        message = rule_validation_message(Translator(language), Error("source must be text"))
        assert "2" in message
        assert "source must be text" not in message


def test_diagnostic_and_settings_errors_have_localized_summaries():
    codes = ("MIXED_SCRIPT", "INLINE_BOUNDARY", "QUOTE_UNBALANCED", "SOURCE_INVALID_XHTML")
    for language in ("en", "zh-Hans", "zh-Hant"):
        translator = Translator(language)
        for code in codes:
            summary = diagnostic_summary(translator, code, count=12)
            assert "12" in summary
            assert code not in summary
        assert settings_error_message(
            translator, ValueError("generic Traditional Chinese requires an explicit Legacy region")
        ) == translator.text("options.region_required")
        assert settings_error_message(
            translator, ValueError("force-pivot must end in the selected configuration")
        ) == translator.text("options.force_pivot_mismatch")
        assert settings_error_message(
            translator, ValueError("profile configuration is unavailable on this host")
        ) == translator.text("profile.config_unavailable")


def test_error_dialog_keeps_original_exception_in_detailed_text():
    class MessageBox:
        instance = None

        def __init__(self, _parent):
            type(self).instance = self

        def setWindowTitle(self, value):
            self.title = value

        def setText(self, value):
            self.summary = value

        def setDetailedText(self, value):
            self.detail = value

        def exec(self):
            self.executed = True

    show_error_details(
        SimpleNamespace(QMessageBox=MessageBox), None, "title", "localized summary",
        "ValueError: original English error",
    )
    assert MessageBox.instance.summary == "localized summary"
    assert MessageBox.instance.detail == "ValueError: original English error"
    assert MessageBox.instance.executed


def test_confirmation_uses_translated_yes_and_no_buttons():
    class MessageBox:
        AcceptRole = 1
        RejectRole = 2
        instance = None

        def __init__(self, _parent):
            type(self).instance = self
            self.buttons = []

        def setWindowTitle(self, _title):
            pass

        def setText(self, _message):
            pass

        def addButton(self, label, role):
            button = SimpleNamespace(label=label, role=role)
            self.buttons.append(button)
            return button

        def setDefaultButton(self, button):
            self.default = button

        def exec(self):
            pass

        def clickedButton(self):
            return self.buttons[0]

    assert ask_confirmation(
        SimpleNamespace(QMessageBox=MessageBox), None, "title", "confirm",
        Translator("zh-Hans"),
    )
    translator = Translator("zh-Hans")
    assert [button.label for button in MessageBox.instance.buttons] == [
        translator.text("common.yes"), translator.text("common.no")]
    assert MessageBox.instance.default is MessageBox.instance.buttons[1]


def test_configuration_labels_translate_standard_and_jieba_ids():
    for language in ("zh-Hans", "zh-Hant"):
        translator = Translator(language)
        label = configuration_label(translator, "s2t")
        assert "s2t" not in label
        assert label in translator.text("config.s2t")
        jieba_label = configuration_label(translator, "s2twp_jieba")
        assert translator.text("config.jieba") in jieba_label
        assert "s2twp_jieba" not in jieba_label


def test_builtin_profile_display_name_follows_ui_language():
    profile = SimpleNamespace(id="conservative", name="Conservative")
    for language in ("zh-Hans", "zh-Hant", "en"):
        translator = Translator(language)
        assert profile_display_name(profile, translator) == translator.text("profile.default_name")


def test_dialogs_share_one_qapplication_instance(monkeypatch):
    class FakeApplication:
        current = None
        created = 0

        @classmethod
        def instance(cls):
            return cls.current

        def __init__(self, _args):
            type(self).created += 1
            type(self).current = self

    class FakeQt:
        QApplication = FakeApplication

    monkeypatch.setattr(qt_helpers, "_application", None)
    first = qt_helpers.ensure_application(FakeQt)
    second = qt_helpers.ensure_application(FakeQt)
    assert first is second
    assert qt_helpers._application is first
    assert FakeApplication.created == 1


def test_progress_reporter_paints_initial_state_immediately():
    events = []

    class Signal:
        def connect(self, callback):
            self.callback = callback

    class FakeApplication:
        @staticmethod
        def processEvents():
            events.append("process-events")

    class FakeProgressDialog:
        def __init__(self, *_args):
            self.canceled = Signal()
            self.minimum_duration = None
            self.value = None
            self.maximum = None
            self.label = None

        def setWindowTitle(self, _title):
            pass

        def setMinimumDuration(self, value):
            self.minimum_duration = value

        def setAutoClose(self, _value):
            pass

        def setAutoReset(self, _value):
            pass

        def setMaximum(self, value):
            self.maximum = value

        def setValue(self, value):
            self.value = value

        def setLabelText(self, value):
            self.label = value

        def show(self):
            events.append("show")

        def close(self):
            pass

    class FakeQt:
        QApplication = FakeApplication
        QProgressDialog = FakeProgressDialog

    reporter = preview_window.ProgressReporter(FakeQt, 3)

    assert reporter.dialog.minimum_duration == 0
    assert reporter.dialog.maximum == 3
    assert reporter.dialog.value == 0
    assert "0/3" in reporter.dialog.label
    assert events == ["show", "process-events"]


def test_result_dialog_explains_files_without_a_write(monkeypatch):
    messages = []

    class MessageBox:
        @staticmethod
        def information(_parent, _title, message):
            messages.append(message)

        @staticmethod
        def warning(_parent, _title, message):
            messages.append(message)

    class FakeQt:
        QMessageBox = MessageBox

    monkeypatch.setattr(preview_window, "load_qt", lambda: FakeQt)
    monkeypatch.setattr(preview_window, "ensure_application", lambda _qt: None)

    preview_window.show_result(
        status="success",
        files_scanned=38,
        files_changed=37,
        accepted_changes=37,
        skipped_changes=0,
        files_without_changes=1,
        translator=Translator("zh-Hans"),
    )

    assert len(messages) == 1
    lines = messages[0].splitlines()
    assert lines[2] == "已分析：38 个文件"
    assert lines[3] == "已写回：37 个文件（应用 37 项修改，跳过 0 项）"
    assert lines[4] == "未写回：1 个文件（其中没有建议变更：1 个）"
    assert lines[6] == "修改已交给 Sigil，请在 Sigil 中检查并保存 EPUB。"

import json
from types import SimpleNamespace

from app.controller import Controller
from app.settings import RunSettings
from app.profiles import Profile, ProfileStore
from core.models import RuleSnapshot as ConversionRuleSnapshot
from rules.engine import convert_with_overlay
from core.preview import PreviewSession
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from tests.support.fake_qt import make_with_table
from ui.rules_window import RuleManagerDialog, RuleWindowResult
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome, _ConversionConfigDialog


class Storage:
    def __init__(self, root):
        self.paths = SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules")


def test_unsaved_default_profile_restores_existing_rulesets_from_run_options(tmp_path):
    rules = RuleStore(tmp_path / "rules")
    rules.save(RuleSet("mine", (Rule(id="custom", source="测试", target="专名",
                                      direction="s2t"),)))
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(),
        {"run_options": {"ruleset_ids": ["default", "mine", "deleted"]}},
        language="en", session_id="test-session",
    )

    assert settings.active.ruleset_ids == ("default", "mine")
    profile = settings.current_profile("s2t", {"ruleset_ids": ["default", "mine", "deleted"]})
    frozen = settings.freeze_rules(profile)
    assert frozen.rules_hash
    assert [rule.id for rule in frozen.rules] == ["custom"]
    assert settings.take_missing_rulesets_notice() == ("deleted",)
    assert settings.take_missing_rulesets_notice() == ()


def test_builtin_tw2sp_protection_covers_bracketed_and_unbracketed_credits(tmp_path):
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(), {},
        language="en", session_id="test-session",
    )

    def official_convert(text):
        return text.replace("威爾", "威尔").replace("著", "着")

    markers = ("◎【著】", "◎著", "◎ 著", "◎　著")
    for config in ("tw2sp", "tw2sp_jieba"):
        snapshot = settings.freeze_rules(Profile(id="test", conversion=config))
        assert isinstance(snapshot, ConversionRuleSnapshot)

        for marker in markers:
            credit = f"安迪·威爾（Andy Weir）{marker}"
            converted = convert_with_overlay(
                credit, official_convert, config=config, snapshot=snapshot,
            )
            assert converted.final == f"安迪·威尔（Andy Weir）{marker}"

        ordinary = convert_with_overlay(
            "奶茶店慰藉著旅者的味蕾", official_convert,
            config=config, snapshot=snapshot,
        )
        assert ordinary.final == "奶茶店慰藉着旅者的味蕾"

    disabled_snapshot = settings.freeze_rules(Profile(
        id="test", conversion="tw2sp", builtin_rules_enabled=False))
    unprotected = convert_with_overlay(
        "安迪·威爾（Andy Weir）◎著",
        lambda text: text.replace("威爾", "威尔").replace("著", "着"),
        config="tw2sp", snapshot=disabled_snapshot,
    )
    assert unprotected.final.endswith("◎着")
    assert not any(rule.id.startswith("builtin-") for rule in disabled_snapshot.rules)


def test_saved_profile_ruleset_ids_win_over_old_run_options(tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    RuleStore(tmp_path / "rules").save(RuleSet("mine"))
    profile = Profile(id="saved", name="Saved", ruleset_ids=("mine",))
    store.save(profile)
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(),
        {"profile_id": "saved", "run_options": {"ruleset_ids": ["old"]}},
        language="en", session_id="test-session",
    )

    assert settings.active.ruleset_ids == ("mine",)
    assert settings.active_profile_is_saved


class Translator:
    def text(self, key, **values):
        return key.format(**values)


class RuleDialogQt:
    class QInputDialog:
        @staticmethod
        def getItem(*_args):
            return "mine", True

    class QMessageBox:
        AcceptRole = 0
        RejectRole = 1
        response = True
        questions = []
        information_messages = []

        def __init__(self, _parent=None):
            type(self).current = self
            self.buttons = []

        def setWindowTitle(self, title):
            self.title = title

        def setText(self, message):
            self.message = message

        def addButton(self, label, role):
            button = SimpleNamespace(label=label, role=role)
            self.buttons.append(button)
            return button

        def setDefaultButton(self, button):
            self.default = button

        def exec(self):
            type(self).questions.append((self.title, self.message))

        def clickedButton(self):
            role = self.AcceptRole if type(self).response else self.RejectRole
            return next(button for button in self.buttons if button.role == role)

        @classmethod
        def information(cls, _parent, title, message):
            cls.information_messages.append((title, message))


def _saved_profile_settings(tmp_path):
    profile_store = ProfileStore(tmp_path / "profiles")
    profile_store.save(Profile(id="saved", name="Saved", ruleset_ids=("default",)))
    adapter = SimpleNamespace(book_fingerprint=lambda: "book-hash")
    backend = SimpleNamespace(available_configs=lambda: {"s2t"})
    settings = RunSettings(
        Storage(tmp_path), adapter,
        {"profile_id": "saved"},
        language="en", session_id="test-session",
    )
    settings.bind_run(settings.active, backend)
    return settings, profile_store


def test_saved_profile_can_confirm_adding_ruleset(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    before = profiles.load("saved")
    RuleDialogQt.QMessageBox.response = True
    RuleDialogQt.QMessageBox.questions = []
    RuleDialogQt.QMessageBox.information_messages = []
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *args, **kwargs:
                        RuleWindowResult("mine", (RuleSet("mine"),)))

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert profiles.load("saved").ruleset_ids == ("default", "mine")
    assert RuleDialogQt.QMessageBox.questions
    assert settings.active.ruleset_ids == ("default", "mine")
    assert before.ruleset_ids == ("default",)


def test_saved_profile_rejection_keeps_change_session_only(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    before = profiles.load("saved")
    RuleDialogQt.QMessageBox.response = False
    RuleDialogQt.QMessageBox.questions = []
    RuleDialogQt.QMessageBox.information_messages = []
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *args, **kwargs:
                        RuleWindowResult("mine", (RuleSet("mine"),)))

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert profiles.load("saved").ruleset_ids == before.ruleset_ids
    assert settings.active.ruleset_ids == ("default", "mine")
    assert RuleDialogQt.QMessageBox.information_messages


def test_renamed_ruleset_id_can_be_reused_without_deleting_the_new_set(
    monkeypatch, tmp_path
):
    profile_store = ProfileStore(tmp_path / "profiles")
    profile = Profile(id="saved", name="Saved", ruleset_ids=("default", "A"))
    profile_store.save(profile)
    rules = RuleStore(tmp_path / "rules")
    rules.save(RuleSet(
        "A", (Rule(id="old", source="旧", target="舊", direction="s2t"),), "Old A"))
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(book_fingerprint=lambda: "book-hash"),
        {"profile_id": "saved"}, language="en", session_id="test-session",
    )
    settings.bind_run(profile, SimpleNamespace(available_configs=lambda: {"s2t"}))
    result = RuleWindowResult(
        "A",
        (
            RuleSet("B", (Rule(id="old", source="旧", target="舊", direction="s2t"),),
                    "Renamed B"),
            RuleSet("A", (Rule(id="new", source="新", target="新", direction="s2t"),),
                    "New A"),
        ),
        renamed=(("A", "B"),),
    )
    RuleDialogQt.QMessageBox.response = True
    monkeypatch.setattr("ui.rules_window.show_rules_window",
                        lambda *_args, **_kwargs: result)

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert (tmp_path / "rules" / "A.json").is_file()
    assert rules.load("A").name == "New A"
    assert rules.load("B").name == "Renamed B"
    assert settings.active.ruleset_ids == ("default", "B", "A")
    assert profile_store.load("saved").ruleset_ids == ("default", "B", "A")


def test_profile_selection_is_validated_before_activation(monkeypatch, tmp_path):
    settings, _profiles = _saved_profile_settings(tmp_path)
    active = settings.active
    selected = Profile(id="new", name="New", conversion="s2t")
    monkeypatch.setattr("ui.profile_window.show_profile_window",
                        lambda *_args, **_kwargs: selected)

    result = settings.pick_profile("s2t", {}, Translator())

    assert result is selected
    assert settings.active is active
    validated = settings.validate_profile(result)
    assert settings.active is active
    settings.commit_profile(validated)
    assert settings.active.id == "new"


def test_unavailable_profile_validation_does_not_change_active_profile(tmp_path):
    settings, _profiles = _saved_profile_settings(tmp_path)
    active = settings.active
    selected = Profile(
        id="jieba", name="Jieba", conversion="s2twp_jieba", segmentation="jieba")

    try:
        settings.validate_profile(selected)
    except ValueError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("unavailable Jieba profile should be rejected")

    assert settings.active is active


class Book:
    def __init__(self):
        self.files = {"a": "<p>测试</p>"}
        self.writes = []

    def text_iter(self):
        yield "a", "a.xhtml"

    def readfile(self, file_id):
        return self.files[file_id]

    def writefile(self, file_id, text):
        self.writes.append((file_id, text))
        self.files[file_id] = text


class NoProgress:
    def update(self, *_args):
        return None

    def cancelled(self):
        return False

    def close(self):
        return None


def _accept_all(planned):
    previews = tuple(PreviewSession(item.plan) for item in planned)
    for preview in previews:
        preview.accept_all()
    return PreviewOutcome(accepted=True, previews=previews)


def test_new_ruleset_is_applied_on_the_next_controller_run(monkeypatch, tmp_path):
    data_dir = tmp_path / "plugin-data"
    qt = make_with_table()
    qt.QInputDialog = SimpleNamespace(getText=lambda *_args, **_kwargs: ("mine", True))
    rule_dialogs = []
    original_rule_init = RuleManagerDialog.__init__

    def capture_rule_dialog(self, *args, **kwargs):
        original_rule_init(self, *args, **kwargs)
        rule_dialogs.append(self)

    monkeypatch.setattr("ui.rules_window.load_qt", lambda: qt)
    monkeypatch.setattr("ui.rules_window.RuleManagerDialog.__init__", capture_rule_dialog)

    def execute_rule_dialog(_widget):
        manager = rule_dialogs[-1]
        manager.new_ruleset_button.click()
        manager.source_edit.setText("测试")
        manager.target_edit.setText("专名")
        manager.add_button.click()
        manager.apply_button.click()

    monkeypatch.setattr("ui.rules_window.exec_dialog", execute_rule_dialog)
    config_dialogs = []
    original_config_init = _ConversionConfigDialog.__init__

    def capture_config_dialog(self, *args, **kwargs):
        original_config_init(self, *args, **kwargs)
        config_dialogs.append(self)

    monkeypatch.setattr(
        "ui.preview_window._ConversionConfigDialog.__init__", capture_config_dialog)
    monkeypatch.setattr("ui.preview_window._load_ui_qt", lambda _translator: qt)

    def execute_config_dialog(widget):
        dialog = next(item for item in config_dialogs if item.dialog is widget)
        if len(config_dialogs) == 1:
            dialog.options_panel._tool("rules")
        dialog._accept()

    monkeypatch.setattr("ui.preview_window.exec_dialog", execute_config_dialog)
    hashes = []
    sources = []

    monkeypatch.setattr("ui.preview_window.choose_scope", lambda _adapter, initial_language, **_kw:
                        ScopeOutcome(True, TargetSelection(Scope.SINGLE, ("a",)),
                                     initial_language))
    monkeypatch.setattr("ui.preview_window.show_preview", lambda planned, **_kwargs: (
        hashes.append(planned[0].plan.rules_snapshot.rules_hash),
        sources.append(tuple(change.rule_source for change in planned[0].plan.changes)),
        _accept_all(planned),
    )[-1])
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", lambda *_args, **_kwargs: NoProgress())
    monkeypatch.setattr("ui.preview_window.show_result", lambda **_kwargs: None)

    first_book = Book()
    second_book = Book()
    assert Controller(first_book, data_dir=data_dir).run() == 0
    preferences = json.loads((data_dir / "preferences.json").read_text(encoding="utf-8"))
    assert "mine" in preferences["run_options"]["ruleset_ids"]
    assert RuleStore(data_dir).load("mine").rules[0].source == "测试"

    assert Controller(second_book, data_dir=data_dir).run() == 0
    assert first_book.writes[0][1] == "<p>专名</p>"
    assert second_book.writes[0][1] == "<p>专名</p>"
    assert hashes[0] == hashes[1]
    assert all(any(value.startswith("UserRule:") for value in run) for run in sources)


def test_deleted_ruleset_is_reported_once_by_controller_and_not_planned(
    monkeypatch, tmp_path
):
    data_dir = tmp_path / "plugin-data"
    controller = Controller(Book(), data_dir=data_dir)
    controller.storage.update_preferences(
        {"run_options": {"ruleset_ids": ["default", "deleted"]}})
    notices = []
    plans = []

    def choose_scope(_adapter, initial_language, *, notice=(), **_kwargs):
        notices.append(tuple(notice))
        return ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("a",)), initial_language
        )

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda *_args, **_kwargs: "s2t",
    )
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda planned, **_kwargs: plans.append(planned) or _accept_all(planned),
    )
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda *_args, **_kwargs: NoProgress())
    monkeypatch.setattr("ui.preview_window.show_result", lambda **_kwargs: None)

    assert controller.run() == 0

    missing_notices = [
        notice for call in notices for notice in call
        if notice[0] == "rulesets_missing"
    ]
    assert missing_notices == [("rulesets_missing", "deleted")]
    assert len(notices) == 1
    assert plans
    assert not any(
        change.rule_source.startswith("UserRule:")
        for item in plans[0] for change in item.plan.changes
    )

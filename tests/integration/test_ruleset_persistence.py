import json
from types import SimpleNamespace

import pytest

from app.errors import RuleConflictError
from app.controller import Controller
from app.settings import RunSettings
from app.profiles import Profile, ProfileStore
from core.models import RuleSnapshot as ConversionRuleSnapshot
from rules.engine import convert_with_overlay
from core.preview import PreviewSession
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator as CatalogTranslator
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


def test_freeze_rules_reports_cross_ruleset_conflict_with_ruleset_ids(tmp_path):
    store = RuleStore(tmp_path / "rules")
    store.save(RuleSet("A", (Rule(
        id="a1", source="软件", target="軟體", direction="s2t"),)))
    store.save(RuleSet("B", (Rule(
        id="b1", source="软件", target="軟件", direction="s2t"),)))
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(), {}, language="en", session_id="test-session")
    profile = Profile(
        id="profile", conversion="s2t", ruleset_ids=("A", "B"),
        builtin_rules_enabled=False,
    )

    with pytest.raises(RuleConflictError) as caught:
        settings.freeze_rules(profile)

    assert caught.value.conflict_groups == ((('a1', 'A'), ('b1', 'B')) ,)
    assert "a1 (A)" in str(caught.value)
    assert "b1 (B)" in str(caught.value)


def test_freeze_rules_ignores_rules_owned_by_another_book_or_profile(tmp_path):
    store = RuleStore(tmp_path / "rules")
    store.save(RuleSet("A", (
        Rule(id="book-a", source="term", target="book A", direction="s2t",
             scope="book", book_fingerprint="other-book"),
        Rule(id="profile-a", source="term", target="profile A", direction="s2t",
             scope="profile", profile_id="other-profile"),
    )))
    store.save(RuleSet("B", (
        Rule(id="book-b", source="term", target="book B", direction="s2t",
             scope="book", book_fingerprint="other-book"),
        Rule(id="profile-b", source="term", target="profile B", direction="s2t",
             scope="profile", profile_id="other-profile"),
    )))
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(), {}, language="en", session_id="test-session")
    profile = Profile(
        id="current-profile", conversion="s2t", ruleset_ids=("A", "B"),
        builtin_rules_enabled=False,
    )

    frozen = settings.freeze_rules(profile)

    assert frozen.rules == ()


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


def test_delete_ruleset_removes_profile_references_and_file(monkeypatch, tmp_path):
    profiles = ProfileStore(tmp_path / "profiles")
    profiles.save(Profile(id="saved", name="Saved", ruleset_ids=("default", "mine")))
    profiles.save(Profile(id="other", name="Other", ruleset_ids=("mine", "default")))
    store = RuleStore(tmp_path / "rules")
    store.save(RuleSet("mine", name="Mine"))
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(book_fingerprint=lambda: "book-hash"),
        {"profile_id": "saved"}, language="en", session_id="test-session")
    monkeypatch.setattr(
        "ui.rules_window.show_rules_window",
        lambda *_args, **_kwargs: RuleWindowResult(
            "default", (RuleSet("default"),), run_ruleset_ids=("default",),
            deleted=("mine",)),
    )

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert settings.active.ruleset_ids == ("default",)
    assert profiles.load("saved").ruleset_ids == ("default",)
    assert profiles.load("other").ruleset_ids == ("default",)
    assert not (store.directory / "mine.json").exists()
    assert settings.take_missing_rulesets_notice() == ()


def test_edit_rules_never_deletes_a_ruleset_saved_in_same_result(monkeypatch, tmp_path):
    profiles = ProfileStore(tmp_path / "profiles")
    profiles.save(Profile(id="saved", name="Saved", ruleset_ids=("default", "X")))
    rule = Rule(id="kept", source="术语", target="專有名詞", direction="s2t")
    store = RuleStore(tmp_path / "rules")
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(book_fingerprint=lambda: "book-hash"),
        {"profile_id": "saved"}, language="en", session_id="test-session")
    result = RuleWindowResult(
        "X", (RuleSet("default"), RuleSet("X", (rule,))),
        run_ruleset_ids=("default", "X"), deleted=("X",))
    monkeypatch.setattr(
        "ui.rules_window.show_rules_window", lambda *_args, **_kwargs: result)

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert store.load("X").rules == (rule,)


def test_saved_profile_can_confirm_adding_ruleset(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    before = profiles.load("saved")
    RuleDialogQt.QMessageBox.response = True
    RuleDialogQt.QMessageBox.questions = []
    RuleDialogQt.QMessageBox.information_messages = []
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *args, **kwargs:
                        RuleWindowResult(
                            "mine", (RuleSet("mine"),),
                            run_ruleset_ids=("default", "mine")))

    settings.edit_rules("s2t", CatalogTranslator("en"), RuleDialogQt, object())

    assert profiles.load("saved").ruleset_ids == ("default", "mine")
    assert len(RuleDialogQt.QMessageBox.questions) == 1
    assert settings.active.ruleset_ids == ("default", "mine")
    assert before.ruleset_ids == ("default",)


def test_confirming_addition_does_not_persist_unconfirmed_removal(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    profiles.save(Profile(id="saved", name="Saved", ruleset_ids=("default", "A")))
    RuleDialogQt.QMessageBox.response = True
    RuleDialogQt.QMessageBox.questions = []
    monkeypatch.setattr(
        "ui.rules_window.show_rules_window", lambda *_args, **_kwargs: RuleWindowResult(
            "N", (RuleSet("default"), RuleSet("N")),
            run_ruleset_ids=("default", "N")))

    settings.edit_rules("s2t", CatalogTranslator("en"), RuleDialogQt, object())

    assert profiles.load("saved").ruleset_ids == ("default", "A", "N")
    assert settings.active.ruleset_ids == ("default", "N")


def test_saved_profile_rejection_keeps_change_session_only(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    before = profiles.load("saved")
    RuleDialogQt.QMessageBox.response = False
    RuleDialogQt.QMessageBox.questions = []
    RuleDialogQt.QMessageBox.information_messages = []
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *args, **kwargs:
                        RuleWindowResult(
                            "mine", (RuleSet("mine"),),
                            run_ruleset_ids=("default", "mine")))

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert profiles.load("saved").ruleset_ids == before.ruleset_ids
    assert settings.active.ruleset_ids == ("default", "mine")
    assert not RuleDialogQt.QMessageBox.information_messages


def test_saved_profile_asks_once_for_multiple_new_rulesets(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    RuleDialogQt.QMessageBox.response = True
    RuleDialogQt.QMessageBox.questions = []
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *args, **kwargs:
                        RuleWindowResult(
                            "mine",
                            (RuleSet("mine", name="Mine"), RuleSet("other", name="Other")),
                            run_ruleset_ids=("default", "mine", "other")))

    settings.edit_rules("s2t", CatalogTranslator("en"), RuleDialogQt, object())

    assert len(RuleDialogQt.QMessageBox.questions) == 1
    _title, message = RuleDialogQt.QMessageBox.questions[0]
    assert "Mine" in message and "Other" in message
    assert profiles.load("saved").ruleset_ids == ("default", "mine", "other")


def test_viewing_other_ruleset_does_not_add_it_to_run(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    RuleDialogQt.QMessageBox.questions = []
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *_args, **_kwargs:
                        RuleWindowResult(
                            "mine", (RuleSet("mine"),),
                            run_ruleset_ids=("default",)))

    settings.edit_rules("s2t", CatalogTranslator("en"), RuleDialogQt, object())

    assert profiles.load("saved").ruleset_ids == ("default",)
    assert settings.active.ruleset_ids == ("default",)
    assert not RuleDialogQt.QMessageBox.questions


def test_disabling_shared_ruleset_asks_when_other_profiles_reference_it(monkeypatch, tmp_path):
    settings, profiles = _saved_profile_settings(tmp_path)
    profiles.save(Profile(
        id="other", name="Other profile", ruleset_ids=("default",)))
    settings.rules.save(RuleSet("default"))
    path = settings.rules.directory / "default.json"
    before = path.read_bytes()
    prompts = []
    managers = []

    def cancel_disable(_qt, _parent, _title, message, _translator):
        prompts.append(message)
        return False

    def open_rules(*args, **kwargs):
        manager = RuleManagerDialog(make_with_table(), args[0], **kwargs)
        managers.append(manager)
        manager.ruleset_enabled_check.setChecked(False)
        manager._apply()
        return manager.result

    monkeypatch.setattr("ui.rules_window.ask_confirmation", cancel_disable)
    monkeypatch.setattr("ui.rules_window.show_rules_window", open_rules)

    settings.edit_rules("s2t", CatalogTranslator("en"), RuleDialogQt, object())

    assert len(prompts) == 1
    assert "Other profile" in prompts[0]
    assert managers[0].ruleset_enabled_check.isChecked()
    assert settings.rules.load("default").enabled
    assert path.read_bytes() == before


def test_clearing_persisted_default_ruleset_saves_empty_rules(monkeypatch, tmp_path):
    settings, _profiles = _saved_profile_settings(tmp_path)
    settings.rules.save(RuleSet("default", (
        Rule(id="old", source="旧词", target="旧目标", direction="s2t"),
    )))
    monkeypatch.setattr(
        "ui.rules_window.show_rules_window",
        lambda *_args, **_kwargs: RuleWindowResult("default", (RuleSet("default"),)),
    )

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert settings.rules.load("default").rules == ()
    reloaded = RunSettings(
        Storage(tmp_path), SimpleNamespace(book_fingerprint=lambda: "book-hash"),
        {"profile_id": "saved"}, language="en", session_id="reloaded",
    )
    assert reloaded.freeze_rules(reloaded.active).rules == ()


def test_clearing_and_disabling_persisted_default_keeps_metadata(monkeypatch, tmp_path):
    settings, _profiles = _saved_profile_settings(tmp_path)
    settings.rules.save(RuleSet("default", (
        Rule(id="old", source="旧词", target="旧目标", direction="s2t"),
    )))
    monkeypatch.setattr(
        "ui.rules_window.show_rules_window",
        lambda *_args, **_kwargs: RuleWindowResult(
            "default", (RuleSet("default", enabled=False),)),
    )

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    saved = settings.rules.load("default")
    assert saved.rules == ()
    assert saved.enabled is False


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


def test_run_ids_from_window_are_not_remapped_after_rename(monkeypatch, tmp_path):
    profiles = ProfileStore(tmp_path / "profiles")
    profiles.save(Profile(id="saved", name="Saved", ruleset_ids=("default", "A")))
    rules = RuleStore(tmp_path / "rules")
    rules.save(RuleSet("A"))
    settings = RunSettings(
        Storage(tmp_path), SimpleNamespace(book_fingerprint=lambda: "book-hash"),
        {"profile_id": "saved"}, language="en", session_id="test-session")
    result = RuleWindowResult(
        "B", (RuleSet("default"), RuleSet("B"), RuleSet("A")),
        renamed=(("A", "B"),), run_ruleset_ids=("default", "B", "A"))
    RuleDialogQt.QMessageBox.response = True
    monkeypatch.setattr(
        "ui.rules_window.show_rules_window", lambda *_args, **_kwargs: result)

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert settings.active.ruleset_ids == ("default", "B", "A")


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
        manager.use_in_run_check.setChecked(True)
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

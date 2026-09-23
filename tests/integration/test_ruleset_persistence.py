import json
from types import SimpleNamespace

from app.controller import Controller
from app.settings import RunSettings
from app.profiles import Profile, ProfileStore
from core.preview import PreviewSession
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from ui.rules_window import RuleWindowResult
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome
from ui.run_options import ConfigurationChoice


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
        Yes = 1
        No = 2
        response = 1
        questions = []
        information_messages = []

        @classmethod
        def question(cls, _parent, title, message, *_args):
            cls.questions.append((title, message))
            return cls.response

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
    RuleDialogQt.QMessageBox.response = RuleDialogQt.QMessageBox.Yes
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
    RuleDialogQt.QMessageBox.response = RuleDialogQt.QMessageBox.No
    RuleDialogQt.QMessageBox.questions = []
    RuleDialogQt.QMessageBox.information_messages = []
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *args, **kwargs:
                        RuleWindowResult("mine", (RuleSet("mine"),)))

    settings.edit_rules("s2t", Translator(), RuleDialogQt, object())

    assert profiles.load("saved").ruleset_ids == before.ruleset_ids
    assert settings.active.ruleset_ids == ("default", "mine")
    assert RuleDialogQt.QMessageBox.information_messages


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
    RuleStore(data_dir).save(RuleSet(
        "mine", (Rule(id="custom", source="测试", target="专名", direction="s2t"),)))
    configurations = iter((
        ConfigurationChoice("s2t", {"ruleset_ids": ["default", "mine"]}),
        ConfigurationChoice("s2t", {}),
    ))
    hashes = []
    sources = []

    monkeypatch.setattr("ui.preview_window.choose_scope", lambda _adapter, initial_language, **_kw:
                        ScopeOutcome(True, TargetSelection(Scope.SINGLE, ("a",)),
                                     initial_language))
    monkeypatch.setattr("ui.preview_window.choose_conversion_config",
                        lambda *_args, **_kwargs: next(configurations))
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

    assert Controller(second_book, data_dir=data_dir).run() == 0
    assert first_book.writes[0][1] == "<p>专名</p>"
    assert second_book.writes[0][1] == "<p>专名</p>"
    assert hashes[0] == hashes[1]
    assert all(any(value.startswith("UserRule:") for value in run) for run in sources)

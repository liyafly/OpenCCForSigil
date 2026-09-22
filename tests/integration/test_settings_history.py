import json
from types import SimpleNamespace

import pytest

from app.controller import Controller
from core.preview import PreviewSession
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome
from ui.run_options import ConfigurationChoice


class Book:
    def __init__(self):
        self.writes = []

    def text_iter(self):
        yield "a", "a.xhtml"

    def readfile(self, _id):
        return "<p>漢字</p>"

    def writefile(self, _id, text):
        self.writes.append(text)


def ui(monkeypatch, config="t2s"):
    monkeypatch.setattr("ui.preview_window.choose_scope", lambda *_args, **_kw: ScopeOutcome(
        True, TargetSelection(Scope.SINGLE, ("a",)), "en"))
    monkeypatch.setattr("ui.preview_window.choose_conversion_config",
                        lambda *_args, **_kw: config)
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", lambda *_args: SimpleNamespace(
        update=lambda *_a: None, close=lambda: None, cancelled=lambda: False))
    monkeypatch.setattr("ui.preview_window.show_result", lambda **_kw: None)


def accept(planned):
    previews = tuple(PreviewSession(item.plan) for item in planned)
    for item in previews:
        item.accept_all()
    return PreviewOutcome(True, previews)


def test_back_to_settings_discards_old_plan_and_rebuilds(monkeypatch, tmp_path):
    book = Book()
    ui(monkeypatch)
    configs = iter(("t2s", "s2t"))
    monkeypatch.setattr("ui.preview_window.choose_conversion_config", lambda *_a, **_kw: next(configs))
    calls = []

    def preview(planned):
        calls.append(planned)
        if len(calls) == 1:
            return SimpleNamespace(accepted=False, previews=(), back_to_settings=True)
        return accept(planned)

    monkeypatch.setattr("ui.preview_window.show_preview", preview)
    assert Controller(book, data_dir=tmp_path).run() == 0
    assert len(calls) == 2
    assert calls[0][0].plan.changes
    assert not calls[1][0].plan.changes
    assert book.writes == []


def test_controller_records_hashes_and_counts_without_document_text(monkeypatch, tmp_path):
    book = Book()
    ui(monkeypatch)
    monkeypatch.setattr("ui.preview_window.show_preview", accept)
    assert Controller(book, data_dir=tmp_path).run() == 0
    history = json.loads((tmp_path / "history/index.json").read_text())
    record = history["sessions"][0]
    assert record["summary"]["changes"] == 1
    assert record["summary"]["config"] == "t2s"
    assert record["commit_manifest"]["files"][0]["change_count"] == 1
    assert "漢字" not in json.dumps(history, ensure_ascii=False)
    assert "汉字" not in json.dumps(history, ensure_ascii=False)


def test_editing_rule_storage_after_preview_blocks_every_book_write(monkeypatch, tmp_path):
    book = Book()
    rules = RuleStore(tmp_path / "rules")
    rules.save(RuleSet("default", (Rule(id="one", source="漢字", target="文本", direction="t2s"),)))
    ui(monkeypatch, ConfigurationChoice("t2s", {"ruleset_ids": ["default"]}))

    def preview(planned):
        rules.save(RuleSet("default", (Rule(id="one", source="漢字", target="不同", direction="t2s"),)))
        return accept(planned)

    monkeypatch.setattr("ui.preview_window.show_preview", preview)
    with pytest.raises(ValueError, match="changed after preview"):
        Controller(book, data_dir=tmp_path).run()
    assert book.writes == []
    assert not (tmp_path / "history/index.json").exists()

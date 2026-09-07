import json

from app.controller import Controller
from core.preview import PreviewSession
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome


class ConversionBook:
    def __init__(self):
        self.files = {"chapter": '<p id="stable">漢字與鼠標</p><script>漢字</script>'}
        self.writes = []

    def text_iter(self):
        yield "chapter", "Text/chapter.xhtml"

    def selected_iter(self):
        yield "manifest", "chapter"

    def readfile(self, file_id):
        return self.files[file_id]

    def writefile(self, file_id, data):
        self.writes.append((file_id, data))


class ScopedBookWithoutSelectionIter:
    """Book fixture whose host has no Book Browser selection API."""

    def __init__(self):
        self.files = {
            "a": "<p>汉字</p>",
            "b": "<p>漢字</p>",
            "c": "<p>软件</p>",
        }
        self.reads = []
        self.writes = []

    def text_iter(self):
        for file_id in self.files:
            yield file_id, f"Text/{file_id}.xhtml"

    def readfile(self, file_id):
        self.reads.append(file_id)
        return self.files[file_id]

    def writefile(self, file_id, data):
        self.writes.append((file_id, data))


def _accept_all_preview(planned):
    previews = tuple(PreviewSession(item.plan) for item in planned)
    for preview in previews:
        preview.accept_all()
    return PreviewOutcome(accepted=True, previews=previews)


class _NoProgress:
    def update(self, _phase, _index, _total, _href):
        return None

    def cancelled(self):
        return False

    def close(self):
        return None


def _patch_scoped_ui(monkeypatch, events=None):
    def choose_scope(adapter, initial_language):
        if events is not None:
            events.append("scope")
        return ScopeOutcome(
            accepted=True,
            selection=TargetSelection(Scope.SINGLE, ("b",)),
            language=initial_language,
        )

    def choose_config(available_configs, default_config):
        if events is not None:
            events.append("direction")
        return "t2s"

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.choose_conversion_config", choose_config)
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", lambda _total: _NoProgress())


def test_controller_runs_preview_stage_verify_commit(monkeypatch, tmp_path):
    book = ConversionBook()

    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda adapter, initial_language: ScopeOutcome(
            accepted=True,
            selection=TargetSelection(Scope.SINGLE, ("chapter",)),
            language=initial_language,
        ),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda available_configs, default_config: "t2s",
    )

    def accept_all(planned):
        previews = tuple(PreviewSession(item.plan) for item in planned)
        for preview in previews:
            preview.accept_all()
        return PreviewOutcome(accepted=True, previews=previews)

    monkeypatch.setattr("ui.preview_window.show_preview", accept_all)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total: _NoProgress()
    )
    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert len(book.writes) == 1
    assert "汉字与鼠标" in book.writes[0][1]
    assert "<script>漢字</script>" in book.writes[0][1]
    assert 'id="stable"' in book.writes[0][1]
    assert '"last_conversion_config": "t2s"' in (
        tmp_path / "plugin-data" / "preferences.json"
    ).read_text(encoding="utf-8")


def test_controller_always_chooses_scope_and_never_reads_or_writes_other_files(
    monkeypatch, tmp_path
):
    book = ScopedBookWithoutSelectionIter()
    events = []
    _patch_scoped_ui(monkeypatch, events)

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert events == ["scope", "direction"]
    assert book.reads == ["b", "b"]
    assert [file_id for file_id, _data in book.writes] == ["b"]


def test_controller_normalizes_null_ui_preferences_before_merging(monkeypatch, tmp_path):
    book = ScopedBookWithoutSelectionIter()
    _patch_scoped_ui(monkeypatch)
    data_dir = tmp_path / "plugin-data"
    data_dir.mkdir()
    (data_dir / "preferences.json").write_text(
        json.dumps({"schema_version": 1, "last_conversion_config": "s2t", "ui": None}),
        encoding="utf-8",
    )

    assert Controller(book, data_dir=data_dir).run() == 0

    saved = json.loads((data_dir / "preferences.json").read_text(encoding="utf-8"))
    assert isinstance(saved["ui"], dict)
    assert saved["ui"]["language"] == "en"

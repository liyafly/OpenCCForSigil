import json

from app.controller import Controller
from app.profiles import Profile, ProfileStore
from core.preview import PreviewSession
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome as _ScopeOutcome
from ui.run_options import ConfigurationChoice


def _scope_outcome(
    accepted,
    selection,
    language,
    *,
    config="t2s",
    options=None,
    preference_options=None,
):
    configuration = None
    if accepted:
        configuration = ConfigurationChoice(
            config, options or {}, preference_options=preference_options
        )
    return _ScopeOutcome(accepted, selection, language, configuration=configuration)

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


def _accept_all_preview(planned, **_kwargs):
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
    def choose_scope(adapter, initial_language, **_kwargs):
        if events is not None:
            events.append("scope")
        return _scope_outcome(
            accepted=True,
            selection=TargetSelection(Scope.SELECTED, ("b",)),
            language=initial_language,
        )

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )


def test_controller_runs_preview_stage_verify_commit(monkeypatch, tmp_path):
    book = ConversionBook()

    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda adapter, initial_language, **_kwargs: _scope_outcome(
            accepted=True,
            selection=TargetSelection(Scope.SELECTED, ("chapter",)),
            language=initial_language,
        ),
    )

    def accept_all(planned, **_kwargs):
        previews = tuple(PreviewSession(item.plan) for item in planned)
        for preview in previews:
            preview.accept_all()
        return PreviewOutcome(accepted=True, previews=previews)

    monkeypatch.setattr("ui.preview_window.show_preview", accept_all)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )
    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert len(book.writes) == 1
    assert "汉字与鼠标" in book.writes[0][1]
    assert "<script>漢字</script>" in book.writes[0][1]
    assert 'id="stable"' in book.writes[0][1]
    assert '"last_conversion_config": "t2s"' in (
        tmp_path / "plugin-data" / "preferences.json"
    ).read_text(encoding="utf-8")


def test_post_preview_progress_covers_noncancellable_writeback(monkeypatch, tmp_path):
    book = ConversionBook()
    reporters = []
    results = []

    class Progress:
        def __init__(self):
            self.phases = []
            self.non_cancellable = False
            self.close_calls = 0

        def disable_cancel(self):
            self.non_cancellable = True

        def update(self, phase, _index, _total, _href):
            self.phases.append(phase)

        def cancelled(self):
            return False

        def close(self):
            self.close_calls += 1

    def create_progress(_total, **_kwargs):
        reporter = Progress()
        reporters.append(reporter)
        return reporter

    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: _scope_outcome(
            True, TargetSelection(Scope.SELECTED, ("chapter",)), initial_language
        ),
    )
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", create_progress)
    monkeypatch.setattr("ui.preview_window.show_result", lambda **values: results.append(values))

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    post_preview = reporters[-1]
    assert post_preview.non_cancellable is True
    assert post_preview.cancelled() is False
    assert {"staging", "verifying", "rechecking", "committing"} <= set(post_preview.phases)
    assert post_preview.close_calls == 1
    assert len(book.writes) == 1
    assert results[-1]["status"] == "success"


def test_controller_always_chooses_scope_and_never_reads_or_writes_other_files(
    monkeypatch, tmp_path
):
    book = ScopedBookWithoutSelectionIter()
    events = []
    _patch_scoped_ui(monkeypatch, events)

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert events == ["scope"]
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


def test_scope_cancel_preserves_checkpoint_and_window_preferences(monkeypatch, tmp_path):
    data_dir = tmp_path / "plugin-data"
    data_dir.mkdir()
    preferences_path = data_dir / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checkpoint_notice": True,
                "ui": {
                    "language": "en",
                    "main_dialog_size": [820, 620],
                    "run_options_advanced_expanded": True,
                },
            }
        ),
        encoding="utf-8",
    )
    book = ConversionBook()

    def cancel_after_hiding(_adapter, initial_language, **kwargs):
        assert "checkpoint_notice_enabled" not in kwargs
        assert "hide_checkpoint_notice" not in kwargs
        return _scope_outcome(False, None, initial_language)

    monkeypatch.setattr("ui.preview_window.choose_scope", cancel_after_hiding)

    assert Controller(book, data_dir=data_dir).run() == 1

    saved = json.loads(preferences_path.read_text(encoding="utf-8"))
    assert saved["checkpoint_notice"] is True
    assert saved["ui"]["main_dialog_size"] == [820, 620]
    assert saved["ui"]["run_options_advanced_expanded"] is True
    assert saved["ui"]["language"] == "en"


def test_cancel_after_profile_delete_does_not_restore_profile_preference(monkeypatch, tmp_path):
    data_dir = tmp_path / "plugin-data"
    data_dir.mkdir()
    ProfileStore(data_dir / "profiles").save(Profile(id="saved", name="Saved"))
    preferences_path = data_dir / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "saved",
                "ui": {"language": "en"},
            }
        ),
        encoding="utf-8",
    )
    book = ConversionBook()

    def cancel_scope(_adapter, initial_language, *, services, translator, **_kwargs):
        services.pick_profile("s2t", {}, translator)
        return _scope_outcome(False, None, initial_language)

    monkeypatch.setattr("ui.preview_window.choose_scope", cancel_scope)

    def delete_profile(_profiles, *, store, on_delete, **_kwargs):
        store._path("saved").unlink()
        on_delete("saved")
        return None

    monkeypatch.setattr("ui.profile_window.show_profile_window", delete_profile)

    assert Controller(book, data_dir=data_dir).run() == 1

    saved = json.loads(preferences_path.read_text(encoding="utf-8"))
    assert saved.get("profile_id") is None


def test_future_profile_selection_is_not_cleared_by_a_completed_run(monkeypatch, tmp_path):
    data_dir = tmp_path / "plugin-data"
    profiles = data_dir / "profiles"
    profiles.mkdir(parents=True)
    profile_path = profiles / "future.json"
    original = '{"schema_version": 2, "id": "future", "conversion": "s2tw"}\n'
    profile_path.write_text(original, encoding="utf-8")
    preferences_path = data_dir / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "future",
                "ui": {"language": "en"},
            }
        ),
        encoding="utf-8",
    )
    book = ConversionBook()
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: _scope_outcome(
            True, TargetSelection(Scope.SELECTED, ("chapter",)), initial_language
        ),
    )
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )
    monkeypatch.setattr("ui.preview_window.show_result", lambda **_kwargs: None)

    assert Controller(book, data_dir=data_dir).run() == 0

    assert json.loads(preferences_path.read_text(encoding="utf-8"))["profile_id"] == "future"
    assert profile_path.read_text(encoding="utf-8") == original
    assert not tuple(profiles.glob("*.corrupt-*"))


def test_controller_reports_unwritten_no_change_files_separately(monkeypatch, tmp_path):
    class AllFilesBook:
        def __init__(self):
            self.files = {
                "already-simplified": "<p>汉字</p>",
                "needs-conversion": "<p>漢字</p>",
            }
            self.writes = []

        def text_iter(self):
            for file_id in self.files:
                yield file_id, f"Text/{file_id}.xhtml"

        def selected_iter(self):
            for file_id in self.files:
                yield "manifest", file_id

        def readfile(self, file_id):
            return self.files[file_id]

        def writefile(self, file_id, data):
            self.writes.append((file_id, data))

    book = AllFilesBook()
    result_calls = []
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda adapter, initial_language, **_kwargs: _scope_outcome(
            accepted=True,
            selection=TargetSelection(Scope.ALL_XHTML, tuple(book.files)),
            language=initial_language,
        ),
    )
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )
    monkeypatch.setattr(
        "ui.preview_window.show_result",
        lambda **values: result_calls.append(values),
    )

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert [file_id for file_id, _data in book.writes] == ["needs-conversion"]
    assert result_calls[-1]["files_scanned"] == 2
    assert result_calls[-1]["files_changed"] == 1
    assert result_calls[-1]["files_not_written"] == 1
    assert result_calls[-1]["files_without_changes"] == 1


def test_malformed_xhtml_is_skipped_while_other_files_convert(monkeypatch, tmp_path):
    class Book:
        def __init__(self):
            self.files = {
                "bad": "<p>汉字<br></p>",
                "good": "<p>漢字</p>",
            }
            self.writes = []

        def text_iter(self):
            for file_id in self.files:
                yield file_id, f"Text/{file_id}.xhtml"

        def readfile(self, file_id):
            return self.files[file_id]

        def writefile(self, file_id, data):
            self.writes.append((file_id, data))

    book = Book()
    planned_seen = []
    result_calls = []
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda adapter, initial_language, **_kwargs: _scope_outcome(
            accepted=True,
            selection=TargetSelection(Scope.ALL_XHTML, tuple(book.files)),
            language=initial_language,
        ),
    )

    def preview(planned, **_kwargs):
        planned_seen.extend(planned)
        return _accept_all_preview(planned)

    monkeypatch.setattr("ui.preview_window.show_preview", preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )
    monkeypatch.setattr(
        "ui.preview_window.show_result", lambda **values: result_calls.append(values)
    )

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    bad, good = planned_seen
    assert bad.source.file_id == "bad"
    assert bad.plan.changes == ()
    assert any(item.code == "SOURCE_INVALID_XHTML" for item in bad.plan.diagnostics)
    assert any(
        item.span is None and "line 1, column" in item.message for item in bad.plan.diagnostics
    )
    invalid_diagnostic = next(
        item for item in bad.plan.diagnostics if item.code == "SOURCE_INVALID_XHTML"
    )
    assert invalid_diagnostic.line == 1
    assert invalid_diagnostic.column == 12
    assert good.source.file_id == "good"
    assert good.plan.changes
    assert [file_id for file_id, _data in book.writes] == ["good"]
    assert result_calls[-1]["files_scanned"] == 2
    assert result_calls[-1]["files_changed"] == 1
    assert result_calls[-1]["diagnostics"][0][:2] == ("Text/bad.xhtml", "SOURCE_INVALID_XHTML")


def test_returning_from_preview_reselects_scope_and_discards_old_plan(monkeypatch, tmp_path):
    class Book:
        def __init__(self):
            self.files = {
                key: f"<p>{value}</p>"
                for key, value in (("a", "漢字"), ("b", "漢字"), ("c", "漢字"))
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

    book = Book()
    scope_calls = []
    preview_plans = []

    def choose_scope(_adapter, initial_language, **_kwargs):
        scope_calls.append(True)
        selected = "a" if len(scope_calls) == 1 else "c"
        return _scope_outcome(
            accepted=True,
            selection=TargetSelection(Scope.SELECTED, (selected,)),
            language=initial_language,
        )

    def show_preview(planned, **_kwargs):
        preview_plans.append(tuple(item.source.file_id for item in planned))
        if len(preview_plans) == 1:
            return PreviewOutcome(accepted=False, previews=(), back_to_settings=True)
        return _accept_all_preview(planned)

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.show_preview", show_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert len(scope_calls) == 2
    assert preview_plans == [("a",), ("c",)]
    assert "b" not in book.reads
    assert [file_id for file_id, _data in book.writes] == ["c"]


def test_cancelling_preview_shows_cancelled_result_without_writing(monkeypatch, tmp_path):
    book = ConversionBook()
    result_calls = []
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: _scope_outcome(
            True, TargetSelection(Scope.SELECTED, ("chapter",)), initial_language
        ),
    )
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda planned, **_kwargs: PreviewOutcome(accepted=False, previews=()),
    )
    monkeypatch.setattr(
        "ui.preview_window.show_result", lambda **values: result_calls.append(values)
    )

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 1

    assert book.writes == []
    assert len(result_calls) == 1
    assert result_calls[0]["status"] == "cancelled"


def test_noop_result_skips_preview_and_offers_scope_return(monkeypatch, tmp_path):
    from opencc_backend.backend import OpenCCBackend

    class NoopBook:
        def __init__(self):
            self.files = {"chapter": "<p>SECRET_DIAGNOSTIC_CONTEXT<br></p>"}
            self.writes = []

        def text_iter(self):
            yield "chapter", "Text/chapter.xhtml"

        def readfile(self, file_id):
            return self.files[file_id]

        def writefile(self, file_id, data):
            self.writes.append((file_id, data))

    book = NoopBook()
    results = []
    converted_book_text = []
    original_convert = OpenCCBackend.convert

    def track_content_conversion(backend, text):
        if text != "汉字":  # The one smoke string used by backend self-test.
            converted_book_text.append(text)
        return original_convert(backend, text)

    monkeypatch.setattr(OpenCCBackend, "convert", track_content_conversion)
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: _scope_outcome(
            True, TargetSelection(Scope.SELECTED, ("chapter",)), initial_language
        ),
    )
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda _planned: (_ for _ in ()).throw(AssertionError("preview must be skipped")),
    )
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )
    monkeypatch.setattr(
        "ui.preview_window.show_result", lambda **values: results.append(values) or "close"
    )

    data_dir = tmp_path / "plugin-data"
    assert Controller(book, data_dir=data_dir).run() == 0

    assert book.writes == []
    assert converted_book_text == []
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["accepted_changes"] == 0
    assert results[0]["return_to_scope"] is True
    assert len(results[0]["diagnostic_documents"]) == 1
    assert [
        diagnostic.code for diagnostic in results[0]["diagnostic_documents"][0].plan.diagnostics
    ] == ["SOURCE_INVALID_XHTML"]
    assert results[0].get("report_text") is None
    log_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (data_dir / "logs").rglob("*")
        if path.is_file()
    )
    assert "SECRET_DIAGNOSTIC_CONTEXT" not in log_text


def test_noop_return_to_scope_restarts_with_new_selection(monkeypatch, tmp_path):
    class NoopThenConvertBook:
        def __init__(self):
            self.files = {"a": "<p>漢字</p>", "c": "<p>汉字</p>"}
            self.writes = []

        def text_iter(self):
            for file_id in self.files:
                yield file_id, f"Text/{file_id}.xhtml"

        def readfile(self, file_id):
            return self.files[file_id]

        def writefile(self, file_id, data):
            self.writes.append((file_id, data))

    book = NoopThenConvertBook()
    scopes = []
    results = []
    previews = []
    config_defaults = []

    def choose_scope(_adapter, initial_language, **kwargs):
        scopes.append(kwargs.get("initial_selection"))
        file_id = "a" if len(scopes) == 1 else "c"
        config_defaults.append(kwargs.get("default_config"))
        return _scope_outcome(
            True, TargetSelection(Scope.SELECTED, (file_id,)), initial_language, config="s2tw"
        )

    def show_result(**values):
        results.append(values)
        return "back_to_scope" if len(results) == 1 else "close"

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.show_result", show_result)
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda planned, **_kwargs: (
            previews.append(tuple(item.source.file_id for item in planned))
            or _accept_all_preview(planned)
        ),
    )
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert len(scopes) == 2
    assert len(config_defaults) == 2
    assert config_defaults[1] == "s2tw"
    assert scopes[0] is None
    assert scopes[1].file_ids == ("a",)
    assert previews == [("c",)]
    assert [file_id for file_id, _data in book.writes] == ["c"]


def test_nav_in_selected_files_is_always_converted(monkeypatch, tmp_path):
    class Book:
        def __init__(self):
            self.files = {
                "chapter": "<p>汉字</p>",
                "nav": "<nav><p>汉字</p></nav>",
            }
            self.writes = []

        def text_iter(self):
            yield "chapter", "Text/chapter.xhtml"
            yield "nav", "Text/nav.xhtml"

        def getnavid(self):
            return "nav"

        def readfile(self, file_id):
            return self.files[file_id]

        def writefile(self, file_id, value):
            self.files[file_id] = value
            self.writes.append(file_id)

    book = Book()
    data_dir = tmp_path / "plugin-data"
    preview_document_kinds = []

    def choose_scope(_adapter, initial_language, **_kwargs):
        return _scope_outcome(
            True,
            TargetSelection(Scope.SELECTED, ("nav",)),
            initial_language,
            config="s2t",
            options={"include_nav": False},
            preference_options={"include_nav": False},
        )

    def show_preview(planned, **_kwargs):
        preview_document_kinds.extend(
            (item.source.file_id, change.document_kind)
            for item in planned for change in item.plan.changes)
        return _accept_all_preview(planned)

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.show_preview", show_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress()
    )
    monkeypatch.setattr("ui.preview_window.show_result", lambda **_kwargs: None)

    assert Controller(book, data_dir=data_dir).run() == 0

    assert ("nav", "nav") in preview_document_kinds
    assert book.writes == ["nav"]

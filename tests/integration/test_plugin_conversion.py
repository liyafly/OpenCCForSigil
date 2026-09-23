import json

from app.controller import Controller
from app.profiles import Profile, ProfileStore
from core.preview import PreviewSession
from sigil.scope import Scope, TargetSelection
from ui.preview_window import ConfigOutcome, PreviewOutcome, ScopeOutcome
from ui.run_options import ConfigurationChoice


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
        return ScopeOutcome(
            accepted=True,
            selection=TargetSelection(Scope.SINGLE, ("b",)),
            language=initial_language,
        )

    def choose_config(available_configs, default_config, **_kwargs):
        if events is not None:
            events.append("direction")
        return "t2s"

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.choose_conversion_config", choose_config)
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())


def test_controller_runs_preview_stage_verify_commit(monkeypatch, tmp_path):
    book = ConversionBook()

    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda adapter, initial_language, **_kwargs: ScopeOutcome(
            accepted=True,
            selection=TargetSelection(Scope.SINGLE, ("chapter",)),
            language=initial_language,
        ),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda available_configs, default_config, **_kwargs: "t2s",
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
            self.close_attempt_ignored = False
            self.cancelled_state = False
            self.close_calls = 0

        def disable_cancel(self):
            self.non_cancellable = True

        def update(self, phase, _index, _total, _href):
            self.phases.append(phase)
            if phase == "staging" and self.non_cancellable:
                # Simulate a close/cancel event while the dialog cannot be
                # cancelled; this must not hide the window or abort writeback.
                self.close_attempt_ignored = True
                self.cancelled_state = False

        def cancelled(self):
            return self.cancelled_state

        def close(self):
            self.close_calls += 1

    def create_progress(_total, **_kwargs):
        reporter = Progress()
        reporters.append(reporter)
        return reporter

    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("chapter",)), initial_language),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda *_args, **_kwargs: "t2s",
    )
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", create_progress)
    monkeypatch.setattr(
        "ui.preview_window.show_result", lambda **values: results.append(values))

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    post_preview = reporters[-1]
    assert post_preview.close_attempt_ignored is True
    assert post_preview.cancelled() is False
    assert {"staging", "verifying", "rechecking", "committing"} <= set(
        post_preview.phases)
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


def test_scope_cancel_preserves_checkpoint_and_window_preferences(monkeypatch, tmp_path):
    data_dir = tmp_path / "plugin-data"
    data_dir.mkdir()
    preferences_path = data_dir / "preferences.json"
    preferences_path.write_text(json.dumps({
        "schema_version": 1,
        "checkpoint_notice": True,
        "ui": {
            "language": "en", "conversion_dialog_size": [820, 620],
            "run_options_advanced_expanded": True,
        },
    }), encoding="utf-8")
    book = ConversionBook()

    def cancel_after_hiding(_adapter, initial_language, **kwargs):
        kwargs["hide_checkpoint_notice"]()
        return ScopeOutcome(False, None, initial_language)

    monkeypatch.setattr("ui.preview_window.choose_scope", cancel_after_hiding)

    assert Controller(book, data_dir=data_dir).run() == 1

    saved = json.loads(preferences_path.read_text(encoding="utf-8"))
    assert saved["checkpoint_notice"] is False
    assert saved["ui"]["conversion_dialog_size"] == [820, 620]
    assert saved["ui"]["run_options_advanced_expanded"] is True
    assert saved["ui"]["language"] == "en"


def test_cancel_after_profile_delete_does_not_restore_profile_preference(
    monkeypatch, tmp_path
):
    data_dir = tmp_path / "plugin-data"
    data_dir.mkdir()
    ProfileStore(data_dir / "profiles").save(
        Profile(id="saved", name="Saved"))
    preferences_path = data_dir / "preferences.json"
    preferences_path.write_text(json.dumps({
        "schema_version": 1, "profile_id": "saved", "ui": {"language": "en"},
    }), encoding="utf-8")
    book = ConversionBook()

    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("chapter",)), initial_language),
    )

    def delete_profile(_profiles, *, store, on_delete, **_kwargs):
        store._path("saved").unlink()
        on_delete("saved")
        return None

    monkeypatch.setattr("ui.profile_window.show_profile_window", delete_profile)

    def cancel_settings(_available, *, services, translator, **_kwargs):
        services.pick_profile("s2t", {}, translator)
        return ConfigOutcome("cancel")

    monkeypatch.setattr("ui.preview_window.choose_conversion_config", cancel_settings)

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
    preferences_path.write_text(json.dumps({
        "schema_version": 1, "profile_id": "future", "ui": {"language": "en"},
    }), encoding="utf-8")
    book = ConversionBook()
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("chapter",)), initial_language),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda *_args, **_kwargs: "t2s",
    )
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())
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
        lambda adapter, initial_language, **_kwargs: ScopeOutcome(
            accepted=True,
            selection=TargetSelection(
                Scope.ALL_XHTML, tuple(book.files)
            ),
            language=initial_language,
        ),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda available_configs, default_config, **_kwargs: "t2s",
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
        lambda adapter, initial_language, **_kwargs: ScopeOutcome(
            accepted=True,
            selection=TargetSelection(Scope.ALL_XHTML, tuple(book.files)),
            language=initial_language,
        ),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda available_configs, default_config, **_kwargs: "t2s",
    )

    def preview(planned, **_kwargs):
        planned_seen.extend(planned)
        return _accept_all_preview(planned)

    monkeypatch.setattr("ui.preview_window.show_preview", preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())
    monkeypatch.setattr(
        "ui.preview_window.show_result", lambda **values: result_calls.append(values))

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    bad, good = planned_seen
    assert bad.source.file_id == "bad"
    assert bad.plan.changes == ()
    assert any(item.code == "SOURCE_INVALID_XHTML" for item in bad.plan.diagnostics)
    assert any(item.span is None and "line 1, column" in item.message
               for item in bad.plan.diagnostics)
    invalid_diagnostic = next(
        item for item in bad.plan.diagnostics if item.code == "SOURCE_INVALID_XHTML")
    assert invalid_diagnostic.line == 1
    assert invalid_diagnostic.column == 11
    assert good.source.file_id == "good"
    assert good.plan.changes
    assert [file_id for file_id, _data in book.writes] == ["good"]
    assert result_calls[-1]["files_scanned"] == 2
    assert result_calls[-1]["files_changed"] == 1
    assert result_calls[-1]["diagnostics"][0][:2] == (
        "Text/bad.xhtml", "SOURCE_INVALID_XHTML")


def test_returning_from_preview_reselects_scope_and_discards_old_plan(
    monkeypatch, tmp_path
):
    class Book:
        def __init__(self):
            self.files = {key: f"<p>{value}</p>" for key, value in (
                ("a", "漢字"), ("b", "漢字"), ("c", "漢字"))}
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
        return ScopeOutcome(
            accepted=True,
            selection=TargetSelection(Scope.SINGLE, (selected,)),
            language=initial_language,
        )

    def show_preview(planned, **_kwargs):
        preview_plans.append(tuple(item.source.file_id for item in planned))
        if len(preview_plans) == 1:
            return PreviewOutcome(accepted=False, previews=(), back_to_settings=True)
        return _accept_all_preview(planned)

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda available_configs, default_config, **_kwargs: "t2s",
    )
    monkeypatch.setattr("ui.preview_window.show_preview", show_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())

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
        lambda _adapter, initial_language, **_kwargs: ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("chapter",)), initial_language),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config",
        lambda *_args, **_kwargs: "t2s",
    )
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda planned, **_kwargs: PreviewOutcome(accepted=False, previews=()),
    )
    monkeypatch.setattr(
        "ui.preview_window.show_result", lambda **values: result_calls.append(values))

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 1

    assert book.writes == []
    assert len(result_calls) == 1
    assert result_calls[0]["status"] == "cancelled"


def test_noop_result_skips_preview_and_offers_scope_return(monkeypatch, tmp_path):
    class NoopBook:
        def __init__(self):
            self.files = {"chapter": "<p>汉字</p>"}
            self.writes = []

        def text_iter(self):
            yield "chapter", "Text/chapter.xhtml"

        def readfile(self, file_id):
            return self.files[file_id]

        def writefile(self, file_id, data):
            self.writes.append((file_id, data))

    book = NoopBook()
    results = []
    monkeypatch.setattr(
        "ui.preview_window.choose_scope",
        lambda _adapter, initial_language, **_kwargs: ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("chapter",)), initial_language),
    )
    monkeypatch.setattr(
        "ui.preview_window.choose_conversion_config", lambda *_args, **_kwargs: "t2s")
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda _planned: (_ for _ in ()).throw(AssertionError("preview must be skipped")),
    )
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())
    monkeypatch.setattr(
        "ui.preview_window.show_result", lambda **values: results.append(values) or "close")

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert book.writes == []
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["accepted_changes"] == 0
    assert results[0]["return_to_scope"] is True


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
        return ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, (file_id,)), initial_language)

    def show_result(**values):
        results.append(values)
        return "back_to_scope" if len(results) == 1 else "close"

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    def choose_config(_available, *, default_config, **_kwargs):
        config_defaults.append(default_config)
        return "s2tw"

    monkeypatch.setattr("ui.preview_window.choose_conversion_config", choose_config)
    monkeypatch.setattr(
        "ui.preview_window.show_result", show_result)
    monkeypatch.setattr(
        "ui.preview_window.show_preview",
        lambda planned, **_kwargs: previews.append(tuple(item.source.file_id for item in planned))
        or _accept_all_preview(planned),
    )
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())

    assert Controller(book, data_dir=tmp_path / "plugin-data").run() == 0

    assert len(scopes) == 2
    assert len(config_defaults) == 2
    assert config_defaults[1] == "s2tw"
    assert scopes[0] is None
    assert scopes[1].file_ids == ("a",)
    assert previews == [("c",)]
    assert [file_id for file_id, _data in book.writes] == ["c"]


def test_settings_back_to_scope_preserves_selected_direction(monkeypatch, tmp_path):
    book = ConversionBook()
    defaults = []
    scope_calls = []

    def choose_scope(_adapter, initial_language, **_kwargs):
        scope_calls.append(True)
        return ScopeOutcome(
            True, TargetSelection(Scope.SINGLE, ("chapter",)), initial_language
        )

    def choose_config(_available, *, default_config, **_kwargs):
        defaults.append(default_config)
        if len(defaults) == 1:
            return ConfigOutcome(
                "back_to_scope",
                ConfigurationChoice("s2tw", {"quotation_mode": "corner"}),
            )
        return None

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.choose_conversion_config", choose_config)

    assert Controller(book, data_dir=tmp_path).run() == 1

    assert len(scope_calls) == 2
    assert defaults[1] == "s2tw"
    preferences = json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))
    assert preferences["last_conversion_config"] == "s2tw"
    assert book.writes == []


def test_nav_preference_is_saved_while_nav_is_outside_scope(monkeypatch, tmp_path):
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
    scope_number = 0
    config_calls = []

    def choose_scope(_adapter, initial_language, **_kwargs):
        nonlocal scope_number
        scope_number += 1
        selection = (
            TargetSelection(Scope.SINGLE, ("chapter",))
            if scope_number == 1
            else TargetSelection(Scope.SELECTED, ("chapter", "nav"))
        )
        return ScopeOutcome(True, selection, initial_language)

    def choose_config(_available, *, initial_options, nav_available, **_kwargs):
        config_calls.append((dict(initial_options), nav_available))
        return ConfigOutcome(
            "continue",
            ConfigurationChoice(
                "s2t", {"include_nav": bool(nav_available)},
                preference_options={"include_nav": True},
            ),
        )

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.choose_conversion_config", choose_config)
    monkeypatch.setattr("ui.preview_window.show_preview", _accept_all_preview)
    monkeypatch.setattr(
        "ui.preview_window.create_progress_reporter", lambda _total, **_kwargs: _NoProgress())
    monkeypatch.setattr("ui.preview_window.show_result", lambda **_kwargs: None)

    assert Controller(book, data_dir=data_dir).run() == 0
    assert Controller(book, data_dir=data_dir).run() == 0

    assert config_calls[0][1] is False
    assert config_calls[1][1] is True
    assert config_calls[1][0]["include_nav"] is True
    assert json.loads((data_dir / "preferences.json").read_text(encoding="utf-8"))[
        "run_options"]["include_nav"] is True

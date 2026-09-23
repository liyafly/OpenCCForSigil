import pytest

from app.controller import Controller
from core.models import Diagnostic, VerificationResult
from core.workflow import WorkflowCommitError, WorkflowError
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome


class Book:
    def __init__(self, files=None, fail_write=None):
        self.files = files or {"a": "<p>汉字</p>"}
        self.fail_write = fail_write
        self.writes = []

    def text_iter(self):
        for file_id in self.files:
            yield file_id, f"Text/{file_id}.xhtml"

    def readfile(self, file_id):
        return self.files[file_id]

    def writefile(self, file_id, value):
        if file_id == self.fail_write:
            raise OSError("simulated write failure")
        self.writes.append(file_id)
        self.files[file_id] = value


class NoProgress:
    def update(self, *_args):
        pass

    def cancelled(self):
        return False

    def close(self):
        pass


def _accept_all(planned):
    from core.preview import PreviewSession

    previews = tuple(PreviewSession(item.plan) for item in planned)
    for preview in previews:
        preview.accept_all()
    return PreviewOutcome(accepted=True, previews=previews)


def _patch_ui(monkeypatch, *, preview_callback=None, results=None, errors=None):
    # Resolve the actual current inventory in the chooser stub so each test
    # converts every file without depending on BookContainer-specific IDs.
    def choose_scope(adapter, initial_language, **_kwargs):
        ids = tuple(file_id for file_id, _href in adapter.text_files(Scope.ALL_XHTML))
        return ScopeOutcome(True, TargetSelection(Scope.ALL_XHTML, ids), initial_language)

    monkeypatch.setattr("ui.preview_window.choose_scope", choose_scope)
    monkeypatch.setattr("ui.preview_window.choose_conversion_config", lambda *_a, **_kw: "s2t")

    def show_preview(planned, **_kwargs):
        if preview_callback:
            preview_callback(planned)
        return _accept_all(planned)

    monkeypatch.setattr("ui.preview_window.show_preview", show_preview)
    monkeypatch.setattr("ui.preview_window.create_progress_reporter", lambda *_a, **_kwargs: NoProgress())
    monkeypatch.setattr("ui.preview_window.show_result", lambda **values: results.append(values)
                        if results is not None else None)
    monkeypatch.setattr("ui.preview_window.show_error", lambda **values: errors.append(values)
                        if errors is not None else None)


def _assert_one_prewrite_error(monkeypatch, tmp_path, book, expected_code, *, preview_callback=None,
                               verify_failure=False):
    errors = []
    _patch_ui(monkeypatch, preview_callback=preview_callback, errors=errors)
    if verify_failure:
        monkeypatch.setattr(
            "core.workflow.verify_staged_file",
            lambda staged, **_kwargs: VerificationResult(
                staged.file_id, False, (Diagnostic("INVALID_XHTML", "bad source"),)),
        )

    with pytest.raises(WorkflowError):
        Controller(book, data_dir=tmp_path).run()

    assert len(errors) == 1
    assert errors[0]["kind"] == expected_code
    assert errors[0]["files_written"] == 0
    assert book.writes == []
    return errors[0]


def test_verify_failure_reports_file_and_diagnostic_before_any_write(monkeypatch, tmp_path):
    error = _assert_one_prewrite_error(
        monkeypatch, tmp_path, Book(), "VERIFY_FAILED", verify_failure=True)

    assert error["affected_files"] == (("Text/a.xhtml", ("INVALID_XHTML",)),)
    assert error["log_path"].endswith(".jsonl")


def test_source_changed_after_preview_is_reported(monkeypatch, tmp_path):
    book = Book()

    def mutate(_planned):
        book.files["a"] = "<p>changed after preview</p>"

    _assert_one_prewrite_error(
        monkeypatch, tmp_path, book, "SOURCE_CHANGED", preview_callback=mutate)


def test_settings_changed_after_preview_is_reported(monkeypatch, tmp_path):
    book = Book()

    def mutate(_planned):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir(exist_ok=True)
        (rules_dir / "changed.json").write_text("{}", encoding="utf-8")

    _assert_one_prewrite_error(
        monkeypatch, tmp_path, book, "SETTINGS_CHANGED", preview_callback=mutate)


def test_partial_write_uses_partial_result_and_not_error_dialog(monkeypatch, tmp_path):
    results = []
    errors = []
    book = Book({"a": "<p>汉字</p>", "b": "<p>汉字</p>"}, fail_write="b")
    _patch_ui(monkeypatch, results=results, errors=errors)

    with pytest.raises(WorkflowCommitError):
        Controller(book, data_dir=tmp_path).run()

    assert results and results[0]["status"] == "partial_failure"
    assert errors == []
    assert book.writes == ["a"]

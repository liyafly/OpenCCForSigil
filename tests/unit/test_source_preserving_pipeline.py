from dataclasses import replace

import pytest

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewError, PreviewFilter, PreviewSession
from core.staging import StagingArea, StagingError
from core.verifier import verify_staged_file
from core.models import ConvertRequest
from core.planner import build_conversion_plan
from core.workflow import ConversionWorkflow, WorkflowCancelled, WorkflowCommitError
from document.tokenizer import tokenize_xhtml
from opencc_backend.backend import OpenCCBackend
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope, TargetSelection


def _plan(source: str) -> ConversionPlan:
    document = tokenize_xhtml(source)
    return build_conversion_plan(
        file_id="chapter.xhtml",
        source=source,
        document=document,
        backend=OpenCCBackend("s2t"),
        request=ConvertRequest("s2t"),
        session_id="session-1",
        profile_id="conservative",
    )


def test_tokenizer_returns_absolute_text_and_allowed_attribute_spans():
    source = (
        '<p id="stable" title="汉语">汉字 &amp; 鼠标</p>'
        '<script>var value = "汉字";</script>'
        "<style>.汉字 { color: red; }</style>"
        "<pre>汉字</pre>"
        '<img alt="软件" src="cover.png" />'
    )

    document = tokenize_xhtml(source)
    values = [(target.source_text, target.attribute_name) for target in document.targets]

    assert ("汉语", "title") in values
    assert ("汉字 ", None) in values
    assert (" 鼠标", None) in values
    assert ("软件", "alt") in values
    assert all("var value" not in target.source_text for target in document.targets)
    assert all("color: red" not in target.source_text for target in document.targets)
    assert all(target.source_text != "汉字" for target in document.targets if target.attribute_name is None)
    for target in document.targets:
        assert source[target.source_start : target.source_end] == target.source_text


def test_plan_stage_and_verify_change_only_planned_spans():
    source = '<p id="stable" title="汉语">汉字与鼠标</p><script>汉字</script>'
    plan = _plan(source)
    staged = StagingArea().stage("chapter.xhtml", source, plan)

    assert 'title="漢語"' in staged.converted
    assert ">漢字與鼠標</p>" in staged.converted
    assert "<script>汉字</script>" in staged.converted
    verification = verify_staged_file(staged)
    assert verification.passed

    tampered = replace(staged, converted=staged.converted.replace('id="stable"', 'id="changed"'))
    assert not verify_staged_file(tampered).passed


def test_preview_requires_explicit_decision_and_supports_accept_this_and_all():
    source = "<p>汉字与鼠标</p>"
    plan = _plan(source)
    preview = PreviewSession(plan)

    with pytest.raises(PreviewError):
        preview.finalize()

    first = preview.changes[0]
    preview.accept_this(first.change_id)
    preview.reject_all(PreviewFilter(category="character"))
    selected = preview.finalize()

    assert selected.changes == (first,)
    assert preview.summary()["undecided"] == 0


def test_preview_accept_all_can_finalize_every_change_without_mutating_original_plan():
    source = "<p>汉字与鼠标</p>"
    plan = _plan(source)
    preview = PreviewSession(plan)

    assert preview.accept_all() == len(plan.changes)
    selected = preview.finalize()

    assert selected.changes == plan.changes
    assert selected is not plan
    assert plan.changes


def test_preview_ui_bulk_overwrite_can_reverse_an_existing_decision():
    plan = _plan("<p>汉字与鼠标</p>")
    preview = PreviewSession(plan)

    first = preview.changes[0]
    preview.reject_this(first.change_id)
    assert preview.accept_all() == len(plan.changes) - 1
    assert preview.decision(first.change_id).value == "reject_this"

    assert preview.accept_all(overwrite=True) == len(plan.changes)
    assert preview.decision(first.change_id).value == "accept_all"
    assert len(preview.finalize().changes) == len(plan.changes)


def test_staging_rejects_source_drift_and_overlapping_changes():
    source = "汉字"
    change = TokenChange("汉", "漢", SourceSpan(0, 1), "OpenCC:s2t", change_id="one")
    plan = ConversionPlan(
        source_sha256="not-the-current-source",
        allowed_spans=(change.span,),
        changes=(change,),
        file_id="chapter.xhtml",
    )
    with pytest.raises(StagingError):
        StagingArea().stage("chapter.xhtml", source, plan)


class FakeBook:
    def __init__(self, source):
        self.source = source
        self.writes = []

    def text_iter(self):
        yield "chapter", "Text/chapter.xhtml"

    def readfile(self, file_id):
        assert file_id == "chapter"
        return self.source

    def writefile(self, file_id, data):
        self.writes.append((file_id, data))


def test_book_workflow_does_not_write_until_verify_then_commit():
    book = FakeBook("<p>汉字与鼠标</p>")
    workflow = ConversionWorkflow(
        SigilBookAdapter(book),
        OpenCCBackend("s2t"),
        ConvertRequest("s2t"),
        session_id="session-1",
        profile_id="conservative",
    )

    planned = workflow.plan()
    previews = workflow.preview()
    assert len(planned) == 1
    assert previews[0].accept_all() == len(planned[0].plan.changes)
    finalized = workflow.finalize(previews)
    staged = workflow.stage(finalized)
    workflow.verify(staged)

    assert book.writes == []
    workflow.commit(staged)
    assert len(book.writes) == 1
    assert "漢字與鼠標" in book.writes[0][1]


def test_workflow_reports_stage_and_verify_progress_and_reuses_source_tokens(monkeypatch):
    book = FakeBook("<p>汉字与鼠标</p>")
    workflow = ConversionWorkflow(
        SigilBookAdapter(book),
        OpenCCBackend("s2t"),
        ConvertRequest("s2t"),
        session_id="session-1",
        profile_id="conservative",
    )

    planned = workflow.plan()
    previews = workflow.preview()
    previews[0].accept_all()
    finalized = workflow.finalize(previews)
    events = []
    staged = workflow.stage(
        finalized,
        progress=lambda phase, index, total, href: events.append(
            (phase, index, total, href)
        ),
    )

    import core.verifier as verifier

    original_tokenize = verifier.tokenize_xhtml
    tokenized_sources = []

    def record_tokenize(source, options=None):
        tokenized_sources.append(source)
        return original_tokenize(source, options)

    monkeypatch.setattr(verifier, "tokenize_xhtml", record_tokenize)
    verification = workflow.verify(
        staged,
        progress=lambda phase, index, total, href: events.append(
            (phase, index, total, href)
        ),
    )

    assert planned[0].tokenized.source == book.source
    assert verification[0].passed
    assert events == [
        ("staging", 1, 1, "Text/chapter.xhtml"),
        ("verifying", 1, 1, "Text/chapter.xhtml"),
    ]
    assert tokenized_sources == [staged[0].converted]


def test_workflow_emits_progress_after_each_operation(monkeypatch):
    book = FakeBook("<p>汉字与鼠标</p>")
    events = []
    original_read = book.readfile

    def readfile(file_id):
        events.append(("read", file_id))
        return original_read(file_id)

    monkeypatch.setattr(book, "readfile", readfile)
    workflow = ConversionWorkflow(
        SigilBookAdapter(book),
        OpenCCBackend("s2t"),
        ConvertRequest("s2t"),
        session_id="session-1",
        profile_id="conservative",
    )
    original_plan_document = workflow._plan_document

    def plan_document(source_document):
        events.append(("plan", source_document.file_id))
        return original_plan_document(source_document)

    monkeypatch.setattr(workflow, "_plan_document", plan_document)

    def progress(phase, index, total, href):
        events.append(("progress", phase, index, total, href))

    workflow.plan(progress=progress)
    assert events == [
        ("read", "chapter"),
        ("progress", "analyzing", 1, 1, "Text/chapter.xhtml"),
        ("plan", "chapter"),
        ("progress", "planning", 1, 1, "Text/chapter.xhtml"),
    ]

    previews = workflow.preview()
    previews[0].accept_all()
    finalized = workflow.finalize(previews)
    events.clear()
    original_stage = workflow.staging.stage

    def stage(file_id, source, plan):
        events.append(("stage", file_id))
        return original_stage(file_id, source, plan)

    monkeypatch.setattr(workflow.staging, "stage", stage)
    staged = workflow.stage(finalized, progress=progress)
    assert events == [
        ("stage", "chapter"),
        ("progress", "staging", 1, 1, "Text/chapter.xhtml"),
    ]

    import core.workflow as workflow_module

    events.clear()
    original_verify = workflow_module.verify_staged_file

    def verify(staged_file, **kwargs):
        events.append(("verify", staged_file.file_id))
        return original_verify(staged_file, **kwargs)

    monkeypatch.setattr(workflow_module, "verify_staged_file", verify)
    workflow.verify(staged, progress=progress)
    assert events == [
        ("verify", "chapter"),
        ("progress", "verifying", 1, 1, "Text/chapter.xhtml"),
    ]


def test_rejected_changes_are_not_written_back_to_sigil():
    book = FakeBook("<p>汉字与鼠标</p>")
    workflow = ConversionWorkflow(
        SigilBookAdapter(book),
        OpenCCBackend("s2t"),
        ConvertRequest("s2t"),
        session_id="session-1",
        profile_id="conservative",
    )

    previews = workflow.preview()
    assert previews[0].reject_all() == len(previews[0].changes)
    finalized = workflow.finalize(previews)
    staged = workflow.stage(finalized)
    workflow.verify(staged)
    workflow.commit(staged)

    assert staged == ()
    assert book.writes == []


class MultiFileBook:
    def __init__(self, *, fail_on: str | None = None):
        self.sources = {
            "a": "<p>汉字</p>",
            "b": "<p>鼠标</p>",
        }
        self.reads = []
        self.writes = []
        self.fail_on = fail_on

    def text_iter(self):
        yield "a", "Text/a.xhtml"
        yield "b", "Text/b.xhtml"

    def readfile(self, file_id):
        self.reads.append(file_id)
        return self.sources[file_id]

    def writefile(self, file_id, data):
        if file_id == self.fail_on:
            raise OSError("controlled write failure")
        self.writes.append((file_id, data))


def test_workflow_cancellation_after_progress_callback_stops_before_next_read():
    book = MultiFileBook()
    workflow = ConversionWorkflow(
        SigilBookAdapter(book),
        OpenCCBackend("s2t"),
        ConvertRequest("s2t"),
        targets=TargetSelection(Scope.ALL_XHTML, ("a", "b")),
    )
    cancelled = False

    def progress(_phase, _index, _total, _href):
        nonlocal cancelled
        cancelled = True

    with pytest.raises(WorkflowCancelled):
        workflow.plan(progress=progress, cancelled=lambda: cancelled)

    assert book.reads == ["a"]
    assert book.writes == []


def test_workflow_reports_partial_write_boundary_failure():
    book = MultiFileBook(fail_on="b")
    workflow = ConversionWorkflow(
        SigilBookAdapter(book),
        OpenCCBackend("s2t"),
        ConvertRequest("s2t"),
        targets=TargetSelection(Scope.ALL_XHTML, ("a", "b")),
    )
    workflow.plan()
    previews = workflow.preview()
    for preview in previews:
        preview.accept_all()
    finalized = workflow.finalize(previews)
    staged = workflow.stage(finalized)
    workflow.verify(staged)

    with pytest.raises(WorkflowCommitError) as raised:
        workflow.commit(staged)

    assert book.writes and book.writes[0][0] == "a"
    assert raised.value.committed_file_ids == ("a",)
    assert raised.value.failed_file_id == "b"

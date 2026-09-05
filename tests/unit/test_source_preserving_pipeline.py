from dataclasses import replace

import pytest

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewError, PreviewFilter, PreviewSession
from core.staging import StagingArea, StagingError
from core.verifier import verify_staged_file
from core.models import ConvertRequest
from core.planner import build_conversion_plan
from core.workflow import ConversionWorkflow
from document.tokenizer import tokenize_xhtml
from opencc_backend.backend import OpenCCBackend
from sigil.adapter import SigilBookAdapter


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

from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.models import ConvertRequest, RuleSnapshot
from core.preview import PreviewSession
from core.staging import apply_changes
from core.workflow import ConversionWorkflow, WorkflowError
from rules.models import Rule, RuleSnapshot as Rules
from sigil.adapter import SigilBookAdapter
from document.tokenizer import TokenizerOptions


class Backend:
    config = "s2t"

    def convert(self, text):
        return text.replace("汉", "漢")

    def convert_for_config(self, config, text):
        return text.replace("漢", "汉") if config == "t2s" else self.convert(text)

    def provenance(self):
        return SimpleNamespace(as_dict=lambda: {"backend": "controlled"})


class Book:
    def __init__(self, source):
        self.source = source
        self.writes = []

    def text_iter(self):
        yield "a", "a.xhtml"

    def readfile(self, _id):
        return self.source

    def writefile(self, _id, source):
        self.writes.append(source)


def request_with_rules(*rules):
    frozen = Rules.freeze(rules)
    return ConvertRequest("s2t", rules_snapshot=RuleSnapshot(
        rules_hash=frozen.sha256, rules=frozen.rules), quotation_mode="corner")


def stage_all(flow):
    planned = flow.plan()
    previews = [PreviewSession(item.plan) for item in planned]
    for preview in previews:
        preview.accept_all()
    staged = flow.stage(flow.finalize(previews))
    flow.verify(staged)
    return planned, staged


def test_protected_and_exact_outputs_bypass_every_later_transform():
    book = Book('<p>保护“汉” 称呼 “汉”</p>')
    request = request_with_rules(
        Rule(id="protect", type="protect", source='保护“汉”', direction="s2t"),
        Rule(id="exact", type="exact", source="称呼", target='“汉字”', direction="s2t"))
    flow = ConversionWorkflow(SigilBookAdapter(book), Backend(), request)
    planned, staged = stage_all(flow)
    assert staged[0].converted == '<p>保护“汉” “汉字” 「漢」</p>'
    assert any(change.rule_source == "UserRule:exact" for change in planned[0].plan.changes)
    assert book.writes == []
    flow.commit(staged)
    assert book.writes == [staged[0].converted]


def test_replacement_text_is_xml_escaped_and_snapshot_guard_precedes_all_writes():
    book = Book('<p title="称呼">称呼</p>')
    request = request_with_rules(Rule(id="exact", source="称呼", target='A & <B> "C"',
                                      direction="s2t"))

    def changed():
        raise ValueError("snapshot changed")

    flow = ConversionWorkflow(SigilBookAdapter(book), Backend(), request, snapshot_guard=changed)
    _, staged = stage_all(flow)
    assert staged[0].converted == '<p title="A &amp; &lt;B> &quot;C&quot;">A &amp; &lt;B> "C"</p>'
    with pytest.raises(WorkflowError, match="snapshot changed") as error:
        flow.commit(staged)
    assert error.value.code == "SETTINGS_CHANGED"
    assert book.writes == []


def test_pivot_is_explicit_high_risk_and_apply_never_reconverts():
    book = Book('<p>漢汉</p>')
    request = ConvertRequest("s2t", pivot_chain=("t2s", "s2t"))
    flow = ConversionWorkflow(SigilBookAdapter(book), Backend(), request)
    planned, staged = stage_all(flow)
    assert all(item.risk == "HIGH" for item in planned[0].plan.changes)
    assert all(item.rule_source == "PivotChain:t2s→s2t" for item in planned[0].plan.changes)
    flow.backend.convert = lambda *_args: pytest.fail("Apply reconverted frozen target")
    flow.commit(staged)
    assert book.writes == ["<p>漢漢</p>"]


def test_rules_hash_mismatch_blocks_plan_and_accept_all_reconstructs_exactly():
    request = request_with_rules(Rule(id="one", source="称呼", target="很长称谓", direction="s2t"))
    flow = ConversionWorkflow(SigilBookAdapter(Book("<p>汉称呼汉</p>")), Backend(), request)
    planned, staged = stage_all(flow)
    assert apply_changes(planned[0].source.source, planned[0].plan.changes) == staged[0].converted
    flow.request = replace(request, rules_snapshot=replace(request.rules_snapshot, rules_hash="bad"))
    with pytest.raises(ValueError, match="hash mismatch"):
        flow.plan()


def test_numeric_reference_opt_in_outputs_characters_and_preserves_named_entities():
    source = '<p title="&#x006c49; &amp;">&#27721; &amp;汉</p>'
    flow = ConversionWorkflow(SigilBookAdapter(Book(source)), Backend(), ConvertRequest("s2t"),
                              tokenizer_options=TokenizerOptions(decode_numeric_cjk_refs=True))
    _, staged = stage_all(flow)
    assert staged[0].converted == '<p title="漢 &amp;">漢 &amp;漢</p>'
    assert all(change.risk == "HIGH" for change in staged[0].plan.changes
               if change.category == "numeric_reference")


def test_inline_boundary_stays_separate_and_has_diagnostic():
    flow = ConversionWorkflow(SigilBookAdapter(Book('<p>汉<em>汉</em>字</p>')),
                              Backend(), ConvertRequest("s2t"))
    planned, staged = stage_all(flow)
    assert staged[0].converted == '<p>漢<em>漢</em>字</p>'
    assert "INLINE_BOUNDARY" in {item.code for item in planned[0].plan.diagnostics}


def test_malformed_xhtml_is_not_written_even_when_lexical_shape_is_unchanged():
    book = Book('<p title="汉" title="字">汉</p>')
    flow = ConversionWorkflow(SigilBookAdapter(book),
                              Backend(), ConvertRequest("s2t"))
    planned, staged = stage_all(flow)
    assert planned[0].plan.changes == ()
    assert "SOURCE_INVALID_XHTML" in {
        diagnostic.code for diagnostic in planned[0].plan.diagnostics
    }
    assert staged == ()
    assert book.writes == []


def test_xhtml_validation_never_fetches_external_dtd_and_keeps_named_entities():
    source = ('<?xml version="1.0"?><!DOCTYPE html SYSTEM "https://invalid.example/no.dtd">'
              '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>汉&nbsp;字</p></body></html>')
    flow = ConversionWorkflow(SigilBookAdapter(Book(source)), Backend(), ConvertRequest("s2t"))
    _, staged = stage_all(flow)
    assert staged[0].converted == source.replace("汉", "漢")


def test_commit_rejects_a_different_buffer_after_verification():
    book = Book("<p>汉</p>")
    flow = ConversionWorkflow(SigilBookAdapter(book), Backend(), ConvertRequest("s2t"))
    _, staged = stage_all(flow)
    forged = replace(staged[0], converted="<p>不属于预览的内容</p>")
    with pytest.raises(RuntimeError, match="changed after verification"):
        flow.commit((forged,))
    assert book.writes == []

import time

from core.models import ConvertRequest, RuleSnapshot
from core.preview import PreviewSession
from core.converter import OfficialBackendConverter
from core.staging import apply_changes
from core.workflow import ConversionWorkflow
from opencc_backend.backend import OpenCCBackend
from rules.models import Rule, RuleSnapshot as Rules
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope, TargetSelection


class Book:
    def __init__(self, source):
        self.source = source
        self.writes = []

    def text_iter(self):
        yield "a", "a.xhtml"

    def readfile(self, _file_id):
        return self.source

    def writefile(self, file_id, source):
        self.writes.append((file_id, source))


def _plan(source, *, rules=(), quotation_mode="corner", detailed_classification=False):
    frozen = Rules.freeze(rules)
    request = ConvertRequest(
        "s2t",
        rules_snapshot=RuleSnapshot(rules_hash=frozen.sha256, rules=frozen.rules),
        quotation_mode=quotation_mode,
        detailed_classification=detailed_classification,
        diagnose_mixed=False,
    )
    book = Book(source)
    backend = OpenCCBackend("s2t")
    workflow = ConversionWorkflow(
        SigilBookAdapter(book), backend, request,
        targets=TargetSelection(Scope.SINGLE, ("a",)),
    )
    planned = workflow.plan()
    backend.close()
    return book, workflow, planned


def _stage_all(workflow, planned):
    previews = [PreviewSession(item.plan) for item in planned]
    for preview in previews:
        preview.accept_all()
    staged = workflow.stage(workflow.finalize(previews))
    verification = workflow.verify(staged)
    return staged, verification


def test_pairing_continues_across_inline_text_targets():
    source = '<p>"他说<em>你好</em>"</p>'
    _book, workflow, planned = _plan(source)
    staged, verification = _stage_all(workflow, planned)

    assert staged[0].converted == '<p>「他說<em>你好</em>」</p>'
    assert verification[0].passed
    assert apply_changes(source, planned[0].plan.changes) == staged[0].converted
    quote_changes = [change for change in planned[0].plan.changes
                     if change.source == '"']
    assert len(quote_changes) == 2
    assert all(change.category == "quotation" for change in quote_changes)
    assert all(change.rule_source == "QuotationTransform" for change in quote_changes)


def test_unbalanced_block_marks_every_quote_change_for_review():
    _book, _workflow, planned = _plan('<p>"甲"乙"</p>')
    quote_changes = [change for change in planned[0].plan.changes
                     if change.category == "quotation"]

    assert [change.target for change in quote_changes] == ["「", "」", "「"]
    assert all(change.risk == "REVIEW" for change in quote_changes)
    assert "QUOTE_UNBALANCED" in {item.code for item in planned[0].plan.diagnostics}


def test_quote_attribution_is_stable_with_detailed_classification():
    source = '<p>"他说<em>你好</em>"</p>'
    _book, _workflow, planned = _plan(source, detailed_classification=True)
    quote_changes = [change for change in planned[0].plan.changes
                     if change.source == '"']

    assert len(quote_changes) == 2
    assert all(change.category == "quotation" for change in quote_changes)
    assert all(change.rule_source == "QuotationTransform" for change in quote_changes)


def test_mixed_opencc_and_quote_opcode_keeps_opencc_attribution():
    class Backend:
        config = "s2t"

        @staticmethod
        def convert(text):
            return text.replace("甲", "乙")

    request = ConvertRequest(
        "s2t", quotation_mode="corner", detailed_classification=False,
        diagnose_mixed=False,
    )
    result = OfficialBackendConverter(Backend()).convert('"甲', request)

    assert result.target == "「乙"
    assert len(result.changes) == 1
    assert result.changes[0].rule_source == "OpenCC:s2t"
    assert result.changes[0].attribution_method == (
        "OpenCC conversion; includes QuotationTransform")


def test_quote_entities_advance_pairing_without_changing_entity_text():
    source = '<p>&#34;甲"</p>'
    _book, workflow, planned = _plan(source)

    staged, verification = _stage_all(workflow, planned)

    assert staged[0].converted == '<p>&#34;甲」</p>'
    assert verification[0].passed
    assert "QUOTE_UNBALANCED" not in {item.code for item in planned[0].plan.diagnostics}


def test_pairing_continues_across_protected_and_exact_rule_spans():
    protected = Rule(id="protect", type="protect", source="软件", direction="s2t")
    _book, workflow, planned = _plan('<p>"软件"</p>', rules=(protected,))
    staged, verification = _stage_all(workflow, planned)
    assert staged[0].converted == '<p>「软件」</p>'
    assert verification[0].passed

    exact = Rule(id="exact", source="鼠标", target="滑鼠", direction="s2t")
    _book, workflow, planned = _plan('<p>"鼠标"</p>', rules=(exact,))
    staged, verification = _stage_all(workflow, planned)
    assert staged[0].converted == '<p>「滑鼠」</p>'
    assert verification[0].passed


def test_pairing_resets_at_block_boundaries_and_marks_unbalanced_quotes():
    source = '<p>"甲</p><p>乙"</p>'
    _book, workflow, planned = _plan(source)
    plan = planned[0].plan

    assert [change.target for change in plan.changes if change.category == "quotation"] == ["「", "「"]
    assert all(change.risk == "REVIEW" for change in plan.changes
               if change.category == "quotation")
    assert "QUOTE_UNBALANCED" in {item.code for item in plan.diagnostics}
    staged, verification = _stage_all(workflow, planned)
    assert staged[0].converted == '<p>「甲</p><p>乙「</p>'
    assert verification[0].passed


def test_attribute_quotes_are_independent_from_body_quotes():
    source = "<img alt='\"甲\"'/><p>\"乙</p>"
    _book, workflow, planned = _plan(source)
    staged, verification = _stage_all(workflow, planned)

    assert staged[0].converted == "<img alt='「甲」'/><p>「乙</p>"
    assert verification[0].passed
    assert all(change.category != "quotation" or change.risk != "REVIEW"
               for change in planned[0].plan.changes if change.target_id.startswith("xhtml:attr:"))


def test_keep_mode_preserves_source_and_creates_no_changes():
    source = '<p>"他说<em>你好</em>"</p>'
    _book, _workflow, planned = _plan(source, quotation_mode="keep")
    quote_changes = [change for change in planned[0].plan.changes
                     if change.category == "quotation"]
    assert quote_changes == []
    staged, verification = _stage_all(_workflow, planned)
    assert staged[0].converted == '<p>"他說<em>你好</em>"</p>'
    assert verification[0].passed


def test_keep_mode_skips_entity_scan(monkeypatch):
    import core.planner

    calls = 0

    def count_calls(*_args, **_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(core.planner, "_feed_quotation_entities", count_calls)
    _plan('<p>&#12288;汉字</p>', quotation_mode="keep")

    assert calls == 0


def test_entity_scan_is_not_quadratic():
    count = 16_000
    source = '<html><body>' + "".join(
        f"<p>&#12288;第{i}段。</p>" for i in range(count)
    ) + "</body></html>"
    started = time.perf_counter()
    _book, _workflow, planned = _plan(source, quotation_mode="corner")

    assert planned
    assert time.perf_counter() - started < 3

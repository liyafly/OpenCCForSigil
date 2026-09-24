from dataclasses import replace

from core.models import ConvertRequest, SourceSpan, TokenChange
from core.planner import build_conversion_plan
from core.staging import StagingArea
from core.verifier import verify_staged_file
from document.tokenizer import tokenize_xhtml
from opencc_backend.backend import OpenCCBackend
from rules.models import Rule, RuleSnapshot


def _plan(source, *rules):
    document = tokenize_xhtml(source)
    request = ConvertRequest(
        "s2t",
        rules_snapshot=RuleSnapshot.freeze(rules),
        detailed_classification=False,
        diagnose_mixed=False,
    )
    plan = build_conversion_plan(
        file_id="chapter.xhtml",
        source=source,
        document=document,
        backend=OpenCCBackend("s2t"),
        request=request,
    )
    return document, plan


def _change(source, text, target, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = source.index(text, start + 1)
    return TokenChange(
        source=text,
        target=target,
        span=SourceSpan(start, start + len(text)),
        rule_source="injected",
        change_id=f"injected-{start}",
    )


def test_normal_plan_passes_with_exact_target_spans():
    source = "<p>术语 KEEP</p>"
    document, plan = _plan(
        source, Rule(id="term", direction="s2t", source="术语", target="專名")
    )
    staged = StagingArea().stage("chapter.xhtml", source, plan)

    result = verify_staged_file(staged, original_document=document)

    assert result.passed
    assert result.diagnostics == ()


def test_unplanned_changes_outside_targets_and_protected_attributes_are_rejected():
    source = (
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><body>'
        '<p epub:type="footnote" role="doc-note">文</p>'
        '<pre>汉字</pre><!--汉字--><script>var a="汉字";</script>'
        '</body></html>'
    )
    document, plan = _plan(source)
    injected = (
        _change(source, "footnote", "endnote"),
        _change(source, "doc-note", "x"),
        _change(source, "汉字", "漢字", 0),
        _change(source, "汉字", "漢字", 1),
        _change(source, "汉字", "漢字", 2),
    )
    plan = replace(plan, changes=injected, allowed_spans=())
    staged = StagingArea().stage("chapter.xhtml", source, plan)

    result = verify_staged_file(staged, original_document=document)
    codes = {item.code for item in result.diagnostics}

    assert not result.passed
    assert "UNPLANNED_CHANGE" in codes
    assert "PROTECTED_ATTRIBUTE_CHANGED" in codes


def test_allowed_span_mismatch_and_unplanned_staged_text_are_reported():
    source = "<p>术语 KEEP</p>"
    document, plan = _plan(
        source, Rule(id="term", direction="s2t", source="术语", target="專名")
    )
    narrowed = replace(plan, allowed_spans=(SourceSpan(0, 1),))
    staged = StagingArea().stage("chapter.xhtml", source, narrowed)
    result = verify_staged_file(staged, original_document=document)
    assert "UNPLANNED_CHANGE" in {item.code for item in result.diagnostics}

    valid_staged = StagingArea().stage("chapter.xhtml", source, plan)
    tampered = replace(valid_staged, converted=valid_staged.converted.replace("KEEP", "ALTERED"))
    tampered_result = verify_staged_file(tampered, original_document=document)

    assert not tampered_result.passed
    assert "UNPLANNED_CHANGE" in {item.code for item in tampered_result.diagnostics}


def test_protected_attribute_signature_covers_namespaces_and_aria_except_label():
    attributes = (
        ("epub:type", "note"),
        ("role", "doc-note"),
        ("xmlns", "urn:one"),
        ("xmlns:epub", "urn:two"),
        ("aria-hidden", "true"),
        ("aria-describedby", "help"),
    )
    for name, value in attributes:
        source = f'<p {name}="{value}">text</p>'
        changed = source.replace(f'{name}="{value}"', f'{name}="changed"')
        assert (
            tokenize_xhtml(source).protected_attribute_signature()
            != tokenize_xhtml(changed).protected_attribute_signature()
        )

    source = '<p aria-label="术语">text</p>'
    changed = source.replace("术语", "專名")
    assert (
        tokenize_xhtml(source).protected_attribute_signature()
        == tokenize_xhtml(changed).protected_attribute_signature()
    )

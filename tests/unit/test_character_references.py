from core.models import SourceSpan
from document.diagnostics import inline_boundary_diagnostics
from document.tokenizer import TokenizerOptions, tokenize_xhtml


def test_numeric_han_references_are_kept_by_default():
    source = "<p>甲&#x6C49;&#27721;&amp;&#169;</p>"
    document = tokenize_xhtml(source)

    assert [target.source_text for target in document.targets] == ["甲"]
    assert all(source[target.source_start : target.source_end] == target.source_text for target in document.targets)


def test_decode_numeric_han_references_exposes_original_entity_spans():
    source = "<p>甲&#x6C49;&#27721;&amp;&#169;乙</p>"
    document = tokenize_xhtml(
        source,
        TokenizerOptions(decode_numeric_cjk_refs=True),
    )

    values = [(target.source_text, target.node_id, target.attribute_name) for target in document.targets]
    assert values == [
        ("甲", "xhtml:text:1", None),
        ("&#x6C49;", "numeric_ref:2", None),
        ("&#27721;", "numeric_ref:3", None),
        ("乙", "xhtml:text:4", None),
    ]
    for target in document.targets:
        assert source[target.source_start : target.source_end] == target.source_text


def test_attribute_entities_are_split_and_named_entities_remain_untargeted():
    source = '<p title="甲&#x6C49;&amp;&#27721;乙">正文</p>'
    document = tokenize_xhtml(
        source,
        TokenizerOptions(decode_numeric_cjk_refs=True),
    )

    attributes = [target for target in document.targets if target.attribute_name == "title"]
    assert [(target.source_text, target.node_id) for target in attributes] == [
        ("甲", "xhtml:attr:1"),
        ("&#x6C49;", "numeric_ref:2"),
        ("&#27721;", "numeric_ref:3"),
        ("乙", "xhtml:attr:4"),
    ]
    assert all(target.attribute_name == "title" for target in attributes)
    assert all(source[target.source_start : target.source_end] == target.source_text for target in attributes)


def test_numeric_reference_targets_never_enter_script_style_or_cdata():
    source = (
        "<script>&#x6C49;</script><style>&#x6C49;</style>"
        "<p><![CDATA[&#x6C49;]]>&#x6C49;</p>"
    )
    document = tokenize_xhtml(source, TokenizerOptions(decode_numeric_cjk_refs=True))

    assert [target.source_text for target in document.targets] == ["&#x6C49;"]
    assert document.targets[0].node_id == "numeric_ref:1"


def test_inline_boundary_diagnostic_reports_without_merging_text_targets():
    source = "<p>头<em>发</em>尾</p>"
    document = tokenize_xhtml(source)

    diagnostics = inline_boundary_diagnostics(document)
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "INLINE_BOUNDARY",
        "INLINE_BOUNDARY",
    ]
    assert diagnostics[0].span == SourceSpan(4, 8)
    assert diagnostics[1].span == SourceSpan(9, 14)


def test_inline_boundary_diagnostic_does_not_cross_block_markup():
    document = tokenize_xhtml("<p>头</p><p>发</p>")

    assert inline_boundary_diagnostics(document) == ()

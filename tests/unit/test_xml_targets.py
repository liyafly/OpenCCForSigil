import pytest
import threading
import time

from document.xml_processor import tokenize_xml, XMLDocumentError
from transforms.language_tags import is_han_language, target_language, with_language_targets
from document.tokenizer import TokenizerOptions, tokenize_xhtml


def test_tokenizer_unicode_i_preserves_offsets_after_raw_text_tags():
    sources = (
        '<html><head><title>İstanbul 游记</title><style>p{漢字}</style></head>'
        '<body><p>汉字</p></body></html>',
        '<html><head><script>var title = "İstanbul 漢字";</script></head>'
        '<body><p>汉字</p></body></html>',
        '<html title="İstanbul"><head><style>p{}</style></head>'
        '<body><p>汉字</p></body></html>',
    )
    results = []

    def tokenize_all():
        for source in sources:
            started = time.perf_counter()
            document = tokenize_xhtml(source)
            results.append((document, time.perf_counter() - started))

    worker = threading.Thread(target=tokenize_all, daemon=True)
    worker.start()
    worker.join(timeout=1)
    assert not worker.is_alive(), "tokenize_xhtml did not return within one second"
    assert len(results) == len(sources)
    for document, elapsed in results:
        texts = [target.source_text for target in document.targets]
        assert elapsed < 1
        assert "汉字" in texts
        assert not any("漢字" in text or "p{}" in text for text in texts)


def test_ncx_keeps_entity_doctype_paths_comments_and_source_offsets():
    source = ('<?xml version="1.0"?>\r\n<!DOCTYPE ncx SYSTEM "no-network.dtd">'
              '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
              '<docTitle><text>汉字&amp;软件&#x6C49;</text></docTitle><!--汉字-->'
              '<navMap><navPoint id="汉字" playOrder="1"><navLabel><text><![CDATA[汉字]]>'
              '</text></navLabel><content src="汉字.xhtml#软件"/></navPoint></navMap></ncx>')
    document = tokenize_xml(source, document_kind="ncx")
    assert [target.source_text for target in document.targets] == ["汉字", "软件", "汉字"]
    for target in document.targets:
        assert source[target.source_start:target.source_end] == target.source_text
    assert document.tags[0].name == "ncx"


def test_metadata_whitelist_resolves_only_author_refinements_and_exact_namespaces():
    source = ('<metadata xmlns="http://www.idpf.org/2007/opf" '
              'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:fake="urn:other">'
              '<meta property="file-as" refines="#author">汉字</meta>'
              '<dc:title id="title">软件</dc:title><dc:creator id="author">汉字</dc:creator>'
              '<dc:identifier>汉字</dc:identifier><dc:language>zh-CN</dc:language>'
              '<dc:rights>汉字</dc:rights><fake:title>汉字</fake:title>'
              '<meta property="file-as" refines="#title">汉字</meta>'
              '<meta property="calibre:series">汉字</meta></metadata>')
    document = tokenize_xml(source, document_kind="metadata", convert_metadata=True)
    assert [target.source_text for target in document.targets] == ["汉字", "软件", "汉字"]
    languages = tokenize_xml(source, document_kind="metadata", include_language=True)
    assert [target.source_text for target in languages.targets] == ["zh-CN"]


@pytest.mark.parametrize("source", [
    '<ncx><navLabel><text>汉字</navLabel></ncx>',
    '<!DOCTYPE ncx [<!ENTITY secret SYSTEM "file:///etc/passwd">]><ncx>&secret;</ncx>',
    '<ncx xmlns="urn:spoof"><navLabel><text>汉字</text></navLabel></ncx>',
])
def test_unsafe_xml_is_blocked(source):
    with pytest.raises(XMLDocumentError):
        tokenize_xml(source, document_kind="ncx")


def test_xml_crlf_astral_offsets_and_namespace_prefixes():
    source = '<n:ncx xmlns:n="http://www.daisy.org/z3986/2005/ncx/"><n:docTitle>' \
             '<n:text>𠮷汉字\r\n软件</n:text></n:docTitle></n:ncx>'
    document = tokenize_xml(source, document_kind="ncx")
    assert ''.join(t.source_text for t in document.targets) == '𠮷汉字软件'
    for target in document.targets:
        assert source[target.source_start:target.source_end] == target.source_text


@pytest.mark.parametrize(
    ("source", "protected_text"),
    (
        ("<m:math><m:mtext>数学</m:mtext></m:math>", "数学"),
        ("<svg:svg><svg:text>图形</svg:text></svg:svg>", "图形"),
        ("<math xmlns='urn:mathml'><mtext>数学</mtext></math>", "数学"),
    ),
)
def test_prefixed_mathml_and_svg_are_protected(source, protected_text):
    document = tokenize_xhtml(source)

    assert protected_text not in [target.source_text for target in document.targets]


def test_prefixed_svg_text_is_writable_when_enabled():
    document = tokenize_xhtml(
        "<svg:svg><svg:text>图形</svg:text></svg:svg>",
        options=TokenizerOptions(svg_text=True),
    )

    assert "图形" in [target.source_text for target in document.targets]


def test_language_modes_do_not_assign_generic_traditional_to_taiwan():
    assert target_language('s2t', 'suggest', 'legacy') is None
    with pytest.raises(ValueError, match='explicit'):
        target_language('s2t', 'force', 'legacy')
    assert target_language('s2t', 'suggest', 'bcp47') == 'zh-Hant'
    assert target_language('s2twp_jieba', 'suggest', 'bcp47') == 'zh-Hant-TW'
    assert target_language('t2s', 'force', 'legacy') == 'zh-CN'
    assert target_language('t2jp', 'force', 'bcp47') is None
    for language in ('zh-Latn', 'zh-Bopo-TW', 'zh-Cyrl', 'en', 'ja'):
        assert not is_han_language(language)
    source = '<html lang="zh-CN" xml:lang="zh-Hans"><p lang="zh-Latn">汉字</p></html>'
    targets = with_language_targets(tokenize_xhtml(source)).targets
    assert [t.source_text for t in targets if t.attribute_name] == ['zh-CN', 'zh-Hans']

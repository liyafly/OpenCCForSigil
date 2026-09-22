import pytest

from document.xml_processor import tokenize_xml, XMLDocumentError
from transforms.language_tags import is_han_language, target_language, with_language_targets
from document.tokenizer import tokenize_xhtml


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

from types import SimpleNamespace

import pytest

from core.models import ConvertRequest
from core.workflow import ConversionWorkflow, WorkflowError
from sigil.adapter import SigilBookAdapter, METADATA_ID
from sigil.scope import Scope, TargetSelection


class Backend:
    config = 's2t'

    def convert(self, source):
        return source.translate(str.maketrans({'汉': '漢', '软': '軟'}))

    def provenance(self):
        return SimpleNamespace(as_dict=lambda: {'config': self.config})


class Book:
    def __init__(self):
        self.files = {
            'chapter': '<html lang="zh-CN" xml:lang="zh-CN"><p>汉字</p></html>',
            'nav': '<html><body><nav><a href="chapter.xhtml#汉字">软件</a></nav></body></html>',
            'ncx': '<ncx><navMap><navPoint id="汉字" playOrder="1"><navLabel><text>软件</text>'
                   '</navLabel><content src="chapter.xhtml#汉字"/></navPoint></navMap></ncx>',
        }
        self.metadata = '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">' \
                        '<dc:title>软件</dc:title><dc:identifier>汉字</dc:identifier>' \
                        '<dc:language>zh-CN</dc:language><dc:language>en</dc:language></metadata>'
        self.reads = []
        self.writes = []

    def getnavid(self):
        return 'nav'

    def text_iter(self):
        return iter((('chapter', 'chapter.xhtml'), ('nav', 'nav.xhtml')))

    def manifest_iter(self):
        return iter((('chapter', 'chapter.xhtml', 'application/xhtml+xml'),
                     ('nav', 'nav.xhtml', 'application/xhtml+xml'),
                     ('ncx', 'toc.ncx', 'application/x-dtbncx+xml')))

    def readfile(self, file_id):
        self.reads.append(file_id)
        return self.files[file_id]

    def writefile(self, file_id, value):
        self.writes.append(file_id)
        self.files[file_id] = value

    def getmetadataxml(self):
        self.reads.append(METADATA_ID)
        return self.metadata

    def setmetadataxml(self, value):
        self.writes.append(METADATA_ID)
        self.metadata = value


def workflow(book, *, extended=True, language=True):
    return ConversionWorkflow(
        SigilBookAdapter(book), Backend(),
        ConvertRequest('s2t', language_tag='zh-Hant' if language else None),
        targets=TargetSelection(Scope.SINGLE, ('chapter',), include_ncx=extended,
                                include_metadata=extended, update_language=language),
    )


def accepted_stage(flow):
    flow.plan()
    previews = flow.preview()
    for preview in previews:
        preview.accept_all()
    staged = flow.stage(flow.finalize(previews))
    flow.verify(staged)
    return staged


def test_explicit_ncx_metadata_language_preview_stage_and_commit():
    book = Book()
    original_ncx, original_metadata = book.files['ncx'], book.metadata
    flow = workflow(book)
    staged = accepted_stage(flow)
    assert not book.writes
    metadata = next(item for item in staged if item.file_id == METADATA_ID)
    assert all(change.risk == 'HIGH' for change in metadata.plan.changes)
    flow.commit(staged)
    assert book.writes == ['chapter', 'ncx', METADATA_ID]
    assert 'nav' not in book.reads
    assert book.files['ncx'] == original_ncx.replace('>软件<', '>軟件<')
    assert book.metadata == original_metadata.replace('>软件<', '>軟件<').replace('>zh-CN<', '>zh-Hant<')
    assert 'lang="zh-Hant" xml:lang="zh-Hant"' in book.files['chapter']


def test_default_scope_never_reads_ncx_or_metadata():
    book = Book()
    flow = workflow(book, extended=False, language=False)
    flow.commit(accepted_stage(flow))
    assert set(book.reads) == {'chapter'}
    assert book.writes == ['chapter']


def test_metadata_changed_after_preview_blocks_all_writes():
    book = Book()
    flow = workflow(book)
    staged = accepted_stage(flow)
    book.metadata = book.metadata.replace('软件', '新标题')
    with pytest.raises(WorkflowError, match='source changed'):
        flow.commit(staged)
    assert not book.writes


def test_language_group_cannot_be_partially_accepted():
    flow = workflow(Book())
    flow.plan()
    previews = flow.preview()
    for preview in previews:
        preview.reject_all()
    language = next(c for c in previews[0].changes if c.group_id)
    previews[0].accept_this(language.change_id)
    with pytest.raises(WorkflowError, match='together'):
        flow.finalize(previews)


@pytest.mark.parametrize(("invalid_target", "invalid_source"), (
    ("ncx", '<ncx><navLabel>汉字</ncx>'),
    ("metadata", '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                  '<dc:title>汉字</metadata>'),
))
def test_malformed_extended_xml_is_skipped_while_other_files_convert(
    invalid_target, invalid_source,
):
    book = Book()
    if invalid_target == "ncx":
        book.files["ncx"] = invalid_source
    else:
        book.metadata = invalid_source

    flow = workflow(book)
    planned = flow.plan()
    invalid = next(item for item in planned if item.source.document_kind == invalid_target)
    diagnostic = next(
        item for item in invalid.plan.diagnostics
        if item.code == "SOURCE_INVALID_XHTML")
    assert invalid.plan.changes == ()
    assert diagnostic.line == 1
    assert invalid_source.index("</") < diagnostic.column <= invalid_source.index("</") + 7
    assert next(item for item in planned if item.source.file_id == "chapter").plan.changes

    previews = flow.preview()
    for preview in previews:
        preview.accept_all()
    staged = flow.stage(flow.finalize(previews))
    flow.verify(staged)
    flow.commit(staged)

    assert invalid.source.source == invalid_source
    assert "chapter" in book.writes
    assert invalid.source.file_id not in book.writes
    invalid_sources = tuple(
        item.source.href for item in planned
        if any(value.code == "SOURCE_INVALID_XHTML" for value in item.plan.diagnostics)
    )
    assert invalid.source.href in invalid_sources

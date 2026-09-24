"""Namespace-aware XML targets with exact source offsets (spec §6/§7.4.4)."""

from bisect import bisect_left
from dataclasses import dataclass
from xml.parsers import expat

from core.models import TextTarget
from document.tokenizer import TokenizedDocument, _find_markup_end, _parse_tag

DC = "http://purl.org/dc/elements/1.1/"
OPF = "http://www.idpf.org/2007/opf"
NCX = "http://www.daisy.org/z3986/2005/ncx/"
METADATA_FIELDS = frozenset({"title", "creator", "contributor", "publisher", "description", "subject"})


class XMLDocumentError(ValueError):
    """Malformed/unsafe XML cannot enter the conversion plan."""


@dataclass
class _Node:
    namespace: str
    name: str
    attributes: dict[str, str]
    parent: "_Node | None"


def _name(value: str) -> tuple[str, str]:
    if "|" in value:
        return tuple(value.rsplit("|", 1))
    return "", value


def tokenize_xml(
    source: str, *, document_kind: str, convert_metadata: bool = False,
    include_language: bool = False, extra_metadata_fields: tuple[str, ...] = (),
) -> TokenizedDocument:
    """Expat validates XML; the lexical scanner only locates raw source spans.

    No serializer is used. Entities, namespace prefixes, declarations and all
    text outside explicitly selected targets remain byte-identical.
    """

    if document_kind not in {"ncx", "metadata"}:
        raise ValueError(f"unsupported XML document kind: {document_kind}")
    if not set(extra_metadata_fields) <= {"rights", "coverage"}:
        raise ValueError("unsupported optional metadata field")
    offsets = [0]
    for character in source:
        offsets.append(offsets[-1] + len(character.encode("utf-8")))
    parser = expat.ParserCreate(namespace_separator="|")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    stack: list[_Node] = []
    nodes: list[_Node] = []
    texts: list[tuple[_Node, int, int]] = []
    tags = []
    in_cdata = False

    def position() -> int:
        return bisect_left(offsets, parser.CurrentByteIndex)

    def start(name, attributes):
        namespace, local = _name(name)
        node = _Node(namespace, local, attributes, stack[-1] if stack else None)
        if not stack:
            expected = "ncx" if document_kind == "ncx" else "metadata"
            allowed_namespace = NCX if document_kind == "ncx" else OPF
            if local != expected or namespace not in {"", allowed_namespace}:
                raise XMLDocumentError(f"expected {expected} XML root")
        nodes.append(node)
        stack.append(node)
        begin = position()
        tag = _parse_tag(source, begin, _find_markup_end(source, begin + 1))
        if tag is None:
            raise XMLDocumentError("XML start tag has no source span")
        tags.append(tag)

    def end(_name):
        begin = position()
        if source.startswith("</", begin):
            tag = _parse_tag(source, begin, _find_markup_end(source, begin + 2))
            if tag is None:
                raise XMLDocumentError("XML end tag has no source span")
            tags.append(tag)
        stack.pop()

    def start_cdata():
        nonlocal in_cdata
        in_cdata = True

    def end_cdata():
        nonlocal in_cdata
        in_cdata = False

    def text(value):
        if in_cdata or not stack or not value:
            return
        begin = position()
        # Entity callbacks contain decoded values, not writable source text.
        if source.startswith("&", begin):
            return
        cursor = begin
        for char in value:
            if char == "\n" and source.startswith("\r\n", cursor):
                cursor += 2
            elif char == "\n" and source.startswith("\r", cursor):
                cursor += 1
            elif cursor < len(source) and source[cursor] == char:
                cursor += 1
            else:
                raise XMLDocumentError("XML text callback does not match its original source")
        texts.append((stack[-1], begin, cursor))

    def reject_entity(*_args):
        raise XMLDocumentError("custom XML entity declarations are not supported")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartCdataSectionHandler = start_cdata
    parser.EndCdataSectionHandler = end_cdata
    parser.CharacterDataHandler = text
    parser.EntityDeclHandler = reject_entity
    parser.ExternalEntityRefHandler = lambda *_args: 1
    try:
        parser.Parse(source.encode("utf-8"), True)
    except (expat.ExpatError, UnicodeError) as exc:
        raise XMLDocumentError(f"invalid {document_kind} XML: {exc}") from exc

    author_ids = {
        node.attributes["id"] for node in nodes
        if node.namespace == DC and node.name in {"creator", "contributor"}
        and node.parent is nodes[0] and "id" in node.attributes
    }
    fields = METADATA_FIELDS | set(extra_metadata_fields)
    targets = []
    for node, begin, end_offset in texts:
        selected = False
        if document_kind == "ncx":
            selected = (
                node.namespace in {"", NCX} and node.name == "text"
                and node.parent is not None and node.parent.namespace in {"", NCX}
                and node.parent.name in {"docTitle", "docAuthor", "navLabel"}
            )
        elif node.parent is nodes[0]:
            selected = convert_metadata and (
                (node.namespace == DC and node.name in fields)
                or (node.namespace in {"", OPF} and node.name == "meta"
                    and node.attributes.get("property") in {"file-as", "alternate-script"}
                    and node.attributes.get("refines", "").removeprefix("#") in author_ids
                    and node.attributes.get("refines", "").startswith("#"))
            )
            selected |= include_language and node.namespace == DC and node.name == "language"
        if selected and source[begin:end_offset].strip():
            targets.append(TextTarget(
                node_id=f"{document_kind}:text:{len(targets) + 1}",
                source_text=source[begin:end_offset], source_start=begin, source_end=end_offset,
                tag_name="dc:language" if node.namespace == DC and node.name == "language"
                else node.name, document_kind=document_kind,
            ))
    return TokenizedDocument(source, tuple(targets), tuple(tags))


def processor_name() -> str:
    return "source_preserving_xml"

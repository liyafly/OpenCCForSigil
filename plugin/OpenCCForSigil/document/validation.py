"""Non-serializing XML syntax checks without loading DTDs or entities."""

import re
from xml.parsers import expat

from document.tokenizer import _find_markup_end


_NAMED_REFERENCE = re.compile(r"&[A-Za-z_:][A-Za-z0-9_.:-]*;")


def validate_xhtml_syntax(source: str) -> None:
    """Check source/fragments, retaining entity spellings in the real document.

    Declarations are excluded from the validation copy; named references are
    represented by a harmless character there. No DTD lookup or entity
    expansion is performed. Numeric references still receive XML validation.
    Wrapping permits the fragment fixtures and Sigil text API fragments.
    """
    fragments = []
    cursor = 0
    while cursor < len(source):
        start = source.find("<", cursor)
        if start < 0:
            fragments.append(source[cursor:])
            break
        fragments.append(source[cursor:start])
        if source.startswith("<!--", start):
            close = source.find("-->", start + 4)
            end = len(source) if close < 0 else close + 3
        elif source.startswith("<![CDATA[", start):
            close = source.find("]]>", start + 9)
            end = len(source) if close < 0 else close + 3
        else:
            end = _find_markup_end(source, start + 1, bracket_aware=True)
        markup = source[start:end]
        if not (re.match(r"<!DOCTYPE\s", markup, re.IGNORECASE) or
                re.match(r"<\?xml\s", markup)):
            fragments.append(markup)
        cursor = max(start + 1, end)
    validation_copy = _NAMED_REFERENCE.sub("x", "".join(fragments))
    parser = expat.ParserCreate(namespace_separator="|")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.ExternalEntityRefHandler = lambda *_args: 0
    try:
        parser.Parse("<validation-root>" + validation_copy + "</validation-root>", True)
    except expat.ExpatError as exc:
        raise ValueError(f"invalid XHTML syntax: {exc}") from exc
